"""
SecureHealth Chain - Standalone Full-Featured REST API Server
Runs using Python Standard Library (zero external dependencies required)
Provides complete API endpoints and serves the interactive Web Dashboard.
"""

import http.server
import socketserver
import json
import csv
import io
import os
import uuid
import datetime
import urllib.parse
import hashlib
import hmac
import secrets
import time
from typing import Dict, Any

from services.crypto_service import calculate_ehr_hash
from services.qr_service import generate_ehr_qr_code
from services.blockchain_ledger import blockchain_ledger

# Dynamic imports
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fl_core")))
try:
    from simulation import run_federated_training
    from risk_model import predict_risk
    HAS_FL_ENGINE = True
    HAS_RISK_MODEL = True
except Exception as e:
    HAS_FL_ENGINE = False
    HAS_RISK_MODEL = False
    predict_risk = None
    print(f"[Warning] FL simulation engine not loaded: {e}")

PORT = int(os.environ.get("SECUREHEALTH_PORT", "5000"))
DEMO_TAMPER_ENABLED = os.environ.get("SECUREHEALTH_ENABLE_TAMPER_DEMO", "").strip().lower() in {"1", "true", "yes"}

# Demo users are hashed at startup; newly registered accounts use the same format.
def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return f"{salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False

USERS_DB = {
    "admin@securehealth.org": {
        "id": 1,
        "name": "System Administrator",
        "email": "admin@securehealth.org",
        "password_hash": hash_password("admin"),
        "role": "admin",
        "hospital_name": "Health Network HQ"
    },
    "doctor@securehealth.org": {
        "id": 2,
        "name": "Dr. Sarah Jenkins",
        "email": "doctor@securehealth.org",
        "password_hash": hash_password("doctor"),
        "role": "doctor",
        "hospital_name": "Metro Health General Hospital"
    },
    "patient@securehealth.org": {
        "id": 3,
        "name": "Aswin Krishna",
        "email": "patient@securehealth.org",
        "password_hash": hash_password("patient"),
        "role": "patient",
        "hospital_name": "Metro Health General Hospital"
    }
}
SESSIONS = {}

EHR_RECORDS_DB = {
    "EHR-DEMO-001": {
        "record_uuid": "EHR-DEMO-001",
        "patient_id": 3,
        "doctor_id": 2,
        "patient_name": "Aswin Krishna",
        "doctor_name": "Dr. Sarah Jenkins",
        "hospital_name": "Metro Health General Hospital",
        "diagnosis": "Cardiovascular Assessment - Normal Sinus Rhythm",
        "clinical_metrics": {
            "age": 48,
            "resting_bp": 122,
            "cholesterol": 195,
            "max_hr": 154,
            "fasting_blood_sugar": 0,
            "angina": 0
        },
        "record_hash": "0x7a8f9c1b2e3d4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f90",
        "blockchain_tx_hash": "0x4b6d91f2c83a74e50d18293746a5b2c1d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8",
        "qr_code_url": "/static/qrcodes/EHR-DEMO-001.svg",
        "created_at": "2026-10-26T20:15:00Z"
    }
}
IOMT_READINGS_DB = []

# Create a demo seal whose database record and ledger hash match each other.
demo_record = EHR_RECORDS_DB["EHR-DEMO-001"]
demo_record["record_hash"] = calculate_ehr_hash(
    demo_record["patient_id"], demo_record["hospital_name"], demo_record["diagnosis"], demo_record["clinical_metrics"]
)
demo_chain_receipt = blockchain_ledger.register_ehr_record("EHR-DEMO-001", demo_record["record_hash"])
demo_record["blockchain_tx_hash"] = demo_chain_receipt["tx_hash"]
demo_record["qr_code_url"] = generate_ehr_qr_code(demo_record)

# No fake training rounds are preloaded; metrics appear after a simulation.

FL_STATE = {
    "total_rounds": 0,
    "current_accuracy": None,
    "last_global_hash": None,
    "last_tx_hash": None,
    "participating_nodes": ["Hospital-A (Apollo)", "Hospital-B (Aster Medcity)", "Hospital-C (City Central)"],
    "privacy_mechanism": "Uncertified Gaussian demonstration noise",
    "history": []
}

AUDIT_LOGS = [
    {
        "id": 1,
        "record_uuid": "EHR-DEMO-001",
        "action": "RECORD_CREATED_AND_SEALED",
        "status": "VERIFIED_AUTHENTIC",
        "timestamp": "2026-10-26T20:15:00Z",
        "details": "Seeded demo record initialized in the local in-memory ledger."
    }
]

EHR_CSV_REQUIRED = {"patient_id", "diagnosis", "age", "resting_bp", "cholesterol"}
CLINICAL_RANGES = {
    "age": (1, 120), "sex": (0, 1), "resting_bp": (40, 300),
    "cholesterol": (50, 1000), "fasting_blood_sugar_mg_dl": (10, 1000),
    "max_hr": (20, 300), "angina": (0, 1),
}
IOMT_METRICS = {
    "heart_rate_bpm": {"unit": "bpm", "range": (20, 250)},
    "systolic_bp_mmhg": {"unit": "mmHg", "range": (40, 300)},
    "spo2_percent": {"unit": "%", "range": (50, 100)},
    "temperature_c": {"unit": "C", "range": (25, 45)},
    "glucose_mg_dl": {"unit": "mg/dL", "range": (10, 1000)},
    "steps_count": {"unit": "steps", "range": (0, 100000)},
}


def registered_patient(patient_id):
    return next((item for item in USERS_DB.values() if item["id"] == patient_id and item["role"] == "patient"), None)


def seal_ehr_record(doctor, patient, diagnosis, clinical_metrics, source_system, recorded_at=None):
    record_uuid = f"EHR-{str(uuid.uuid4())[:8].upper()}"
    hospital_name = doctor["hospital_name"]
    clinical_metrics = dict(clinical_metrics)
    # Retain the latest raw IoMT observations in the sealed EHR snapshot.
    latest_by_metric = {}
    for reading in IOMT_READINGS_DB:
        if reading["patient_id"] == patient["id"]:
            metric = reading["metric"]
            if metric not in latest_by_metric or reading["observed_at"] > latest_by_metric[metric]["observed_at"]:
                latest_by_metric[metric] = reading
    if latest_by_metric:
        clinical_metrics["iomt_observations"] = [
            {key: value for key, value in reading.items() if key not in ("patient_name",)}
            for reading in latest_by_metric.values()
        ]

    record_hash = calculate_ehr_hash(patient["id"], hospital_name, diagnosis, clinical_metrics)
    ledger_receipt = blockchain_ledger.register_ehr_record(record_uuid, record_hash)
    tx_hash = ledger_receipt["tx_hash"]
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "record_uuid": record_uuid, "patient_id": patient["id"], "doctor_id": doctor["id"],
        "patient_name": patient["name"], "doctor_name": doctor["name"], "hospital_name": hospital_name,
        "diagnosis": diagnosis, "clinical_metrics": clinical_metrics, "record_hash": record_hash,
        "blockchain_tx_hash": tx_hash, "qr_code_url": generate_ehr_qr_code({
            "record_uuid": record_uuid, "patient_id": patient["id"], "record_hash": record_hash,
            "blockchain_tx_hash": tx_hash,
        }), "created_at": created_at, "recorded_at": recorded_at or created_at,
        "source_system": source_system,
    }
    EHR_RECORDS_DB[record_uuid] = record
    AUDIT_LOGS.append({
        "id": len(AUDIT_LOGS) + 1, "record_uuid": record_uuid, "action": "EHR_HASH_SEALED_LOCAL",
        "status": "VERIFIED_AUTHENTIC", "timestamp": created_at,
        "details": f"Imported from {source_system}; local demo-ledger transaction {tx_hash[:16]}...",
    })
    return record

class SecureHealthHandler(http.server.BaseHTTPRequestHandler):
    def authenticated_user(self):
        header = self.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        session = SESSIONS.get(token)
        if not session or session["expires_at"] < time.time():
            SESSIONS.pop(token, None)
            return None
        return session["user"]

    def require_role(self, *roles):
        user = self.authenticated_user()
        if not user:
            self.send_json(401, {"success": False, "message": "Sign in to continue"})
            return None
        if roles and user["role"] not in roles:
            self.send_json(403, {"success": False, "message": "Your account role cannot perform this action"})
            return None
        return user

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, status_code: int, data: Dict[str, Any]):
        response = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(response)

    def serve_file(self, file_path: str, content_type: str):
        if not os.path.exists(file_path):
            self.send_error(404, "File Not Found")
            return
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def parse_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            raw = self.rfile.read(length).decode("utf-8")
            try:
                return json.loads(raw)
            except Exception:
                return {}
        return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/me":
            user = self.authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "message": "Session expired"})
            else:
                self.send_json(200, {"success": True, "user": user})
            return

        # Serve Frontend UI
        if path == "/" or path == "/index.html":
            static_dir = os.path.join(os.path.dirname(__file__), "static")
            index_path = os.path.join(static_dir, "index.html")
            self.serve_file(index_path, "text/html")
            return

        # Serve QR Codes
        if path.startswith("/static/qrcodes/"):
            viewer = self.require_role("doctor", "patient")
            if not viewer:
                return
            file_name = os.path.basename(path)
            record_uuid = os.path.splitext(file_name)[0]
            record = EHR_RECORDS_DB.get(record_uuid)
            if not record:
                self.send_error(404, "QR record not found")
                return
            if viewer["role"] == "patient" and str(record["patient_id"]) != str(viewer["id"]):
                self.send_json(403, {"success": False, "message": "Patients can only open QR codes for their own records"})
                return
            if viewer["role"] == "doctor" and record.get("hospital_name") != viewer.get("hospital_name"):
                self.send_json(403, {"success": False, "message": "You can only open QR codes from your hospital"})
                return
            if not file_name.endswith((".png", ".svg")):
                self.send_error(404, "QR file not found")
                return
            file_path = os.path.join(os.path.dirname(__file__), "static", "qrcodes", file_name)
            mime = "image/svg+xml" if file_name.endswith(".svg") else "image/png"
            self.serve_file(file_path, mime)
            return

        # API: EHR List
        if path == "/api/ehr/list":
            user = self.require_role("doctor", "patient")
            if not user:
                return
            records = list(EHR_RECORDS_DB.values())
            if user["role"] == "patient":
                # Patients can only read records owned by their authenticated account.
                records = [record for record in records if str(record["patient_id"]) == str(user["id"])]
            else:
                # Doctors are limited to records at their assigned hospital.
                records = [record for record in records if record.get("hospital_name") == user.get("hospital_name")]
                requested_patient = urllib.parse.parse_qs(parsed.query).get("patient_id", [None])[0]
                if requested_patient:
                    patient = next((item for item in USERS_DB.values()
                                    if str(item["id"]) == str(requested_patient)
                                    and item["role"] == "patient"
                                    and item.get("hospital_name") == user.get("hospital_name")), None)
                    if not patient:
                        self.send_json(403, {"success": False, "message": "That patient is outside your hospital"})
                        return
                    records = [record for record in records if str(record["patient_id"]) == str(patient["id"])]
            self.send_json(200, {"success": True, "records": records})
            return

        if path == "/api/ehr/patients":
            doctor = self.require_role("doctor")
            if not doctor:
                return
            patients = [
                {"id": patient["id"], "name": patient["name"]}
                for patient in USERS_DB.values()
                if patient["role"] == "patient"
                and patient.get("hospital_name") == doctor.get("hospital_name")
            ]
            self.send_json(200, {"success": True, "patients": patients})
            return

        # API: FL Status and administrator-only update verification
        if path == "/api/fl/status":
            if not self.require_role("admin"):
                return
            self.send_json(200, {"success": True, "fl_state": FL_STATE})
            return

        if path == "/api/fl/verify":
            if not self.require_role("admin"):
                return
            reports = []
            for round_data in FL_STATE["history"]:
                round_number = round_data["round"]
                expected = {
                    update["hospital"]: update["update_hash"]
                    for update in round_data.get("node_updates", [])
                }
                recorded = {
                    update["node"]: update["model_hash"]
                    for update in blockchain_ledger.fl_round_updates.get(round_number, [])
                }
                node_updates_match = bool(expected) and all(recorded.get(node) == model_hash for node, model_hash in expected.items())
                global_model_match = (
                    blockchain_ledger.global_models.get(round_number)
                    == round_data.get("global_model_hash")
                )
                reports.append({
                    "round": round_number,
                    "verified": node_updates_match and global_model_match,
                    "node_updates_match": node_updates_match,
                    "global_model_match": global_model_match,
                    "node_count": len(expected),
                    "global_model_hash": round_data.get("global_model_hash"),
                })
            self.send_json(200, {
                "success": True,
                "verified_rounds": sum(1 for report in reports if report["verified"]),
                "total_rounds": len(reports),
                "rounds": reports,
            })
            return

        # API: Blockchain Blocks & Ledger State
        if path == "/api/blockchain/blocks":
            if not self.require_role("admin"):
                return
            self.send_json(200, {
                "success": True,
                "contract_address": blockchain_ledger.contract_address,
                "is_live_ganache": blockchain_ledger.check_live_ganache(),
                "transactions_recorded_on_ganache": False,
                "consensus_protocol": "In-memory demo ledger (no consensus protocol)",
                "total_blocks": len(blockchain_ledger.chain),
                "blocks": blockchain_ledger.get_blocks()
            })
            return

        # API: Admin Stats & System Audit
        if path == "/api/admin/stats":
            if not self.require_role("admin"):
                return
            self.send_json(200, {
                "success": True,
                "stats": {
                    "total_records": len(EHR_RECORDS_DB),
                    "total_users": len(USERS_DB),
                    "fl_rounds": FL_STATE["total_rounds"],
                    "global_model_accuracy": f"{FL_STATE['current_accuracy']}%",
                    "blockchain_network": "Local in-memory demo ledger",
                    "contract_status": "NOT_CONNECTED",
                    "audit_logs": [
                        {key: entry.get(key) for key in ("id", "action", "status", "timestamp")}
                        for entry in AUDIT_LOGS[-50:]
                    ]
                }
            })
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.parse_body()

        # ==========================================
        # 1. AUTHENTICATION (MODULE 1)
        # ==========================================
        if path == "/api/auth/login":
            email = body.get("email", "").strip().lower()
            password = body.get("password", "")
            user = USERS_DB.get(email)
            if not user or not verify_password(password, user["password_hash"]):
                self.send_json(401, {"success": False, "message": "Invalid email or password"})
                return
            token = secrets.token_urlsafe(32)
            safe_user = {key: user[key] for key in ("id", "name", "email", "role", "hospital_name")}
            SESSIONS[token] = {"user": safe_user, "expires_at": time.time() + 8 * 60 * 60}
            self.send_json(200, {
                "success": True,
                "user": safe_user,
                "token": token
            })
            return

        if path == "/api/auth/register":
            email = body.get("email", "").strip().lower()
            name = body.get("name", "").strip()
            password = body.get("password", "")
            hospital_name = body.get("hospital_name", "Metro Health General Hospital").strip()
            if not email or "@" not in email or not name or len(password) < 8:
                self.send_json(400, {"success": False, "message": "Enter a valid email, name, and password with at least 8 characters"})
                return
            if email in USERS_DB:
                self.send_json(409, {"success": False, "message": "An account with this email already exists"})
                return
            new_id = max((user["id"] for user in USERS_DB.values()), default=0) + 1
            USERS_DB[email] = {"id": new_id, "name": name, "email": email, "password_hash": hash_password(password), "role": "patient", "hospital_name": hospital_name}
            self.send_json(201, {"success": True, "message": "Patient account created. Sign in to continue."})
            return

        if path == "/api/auth/logout":
            if not self.require_role("admin", "doctor", "patient"):
                return
            header = self.headers.get("Authorization", "")
            _, _, token = header.partition(" ")
            SESSIONS.pop(token, None)
            self.send_json(200, {"success": True})
            return

        # ==========================================
        # 2. AI RISK PREDICTION (MODULE 2 & 4)
        # ==========================================
        if path == "/api/ai/predict-risk":
            if not self.require_role("doctor"):
                return
            if not HAS_RISK_MODEL:
                self.send_json(503, {"success": False, "message": "The sample risk model dependencies are unavailable"})
                return
            try:
                result = predict_risk(body.get("age", 45), body.get("resting_bp", 120), body.get("cholesterol", 200), body.get("max_hr", 150), body.get("angina", 0))
            except (TypeError, ValueError) as error:
                self.send_json(400, {"success": False, "message": str(error)})
                return
            self.send_json(200, {"success": True, **result})
            return

        # ==========================================
        # 3. EHR CREATION & BLOCKCHAIN SEALING (MODULE 3 & 4)
        # ==========================================
        if path == "/api/ehr/create":
            user = self.require_role("doctor")
            if not user:
                return
            try:
                patient_id = int(body.get("patient_id", 3))
            except (TypeError, ValueError):
                self.send_json(400, {"success": False, "message": "Choose a valid patient"})
                return
            patient = next((item for item in USERS_DB.values() if item["id"] == patient_id and item["role"] == "patient"), None)
            if not patient:
                self.send_json(400, {"success": False, "message": "Choose a registered patient"})
                return
            if patient.get("hospital_name") != user.get("hospital_name"):
                self.send_json(403, {"success": False, "message": "You can only create records for patients at your hospital"})
                return
            doctor_id = user["id"]
            doctor_name = user["name"]
            patient_name = patient["name"]
            hospital_name = user["hospital_name"]
            diagnosis = body.get("diagnosis", "Normal Health Checkup")
            clinical_metrics = body.get("clinical_metrics", {})

            record_uuid = f"EHR-{str(uuid.uuid4())[:8].upper()}"

            # Calculate deterministic SHA-256 hash
            record_hash = calculate_ehr_hash(patient_id, hospital_name, diagnosis, clinical_metrics)

            # Store the hash in the local in-memory demo ledger.
            bc_result = blockchain_ledger.register_ehr_record(record_uuid, record_hash)
            tx_hash = bc_result.get("tx_hash")

            # Generate QR Code
            qr_url = generate_ehr_qr_code({
                "record_uuid": record_uuid,
                "patient_id": patient_id,
                "record_hash": record_hash,
                "blockchain_tx_hash": tx_hash
            })

            new_record = {
                "record_uuid": record_uuid,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "patient_name": patient_name,
                "doctor_name": doctor_name,
                "hospital_name": hospital_name,
                "diagnosis": diagnosis,
                "clinical_metrics": clinical_metrics,
                "record_hash": record_hash,
                "blockchain_tx_hash": tx_hash,
                "qr_code_url": qr_url,
                "created_at": datetime.datetime.now().isoformat()
            }
            EHR_RECORDS_DB[record_uuid] = new_record

            AUDIT_LOGS.append({
                "id": len(AUDIT_LOGS) + 1,
                "record_uuid": record_uuid,
                "action": "EHR_HASH_SEALED_LOCAL",
                "status": "VERIFIED_AUTHENTIC",
                "timestamp": datetime.datetime.now().isoformat(),
                "details": f"Created by {doctor_name} at {hospital_name}. Local demo-ledger transaction: {tx_hash[:16]}..."
            })

            self.send_json(201, {"success": True, "record": new_record})
            return

        # ==========================================
        # 4. QR VERIFICATION & TAMPER PROOF (MODULE 4)
        # ==========================================
        if path == "/api/verify/record":
            if not self.require_role("doctor", "patient"):
                return
            record_uuid = body.get("record_uuid")
            if not record_uuid or record_uuid not in EHR_RECORDS_DB:
                self.send_json(404, {"success": False, "message": "Record ID not found on system"})
                return

            record = EHR_RECORDS_DB[record_uuid]
            viewer = self.authenticated_user()
            if viewer["role"] == "patient" and str(record["patient_id"]) != str(viewer["id"]):
                self.send_json(403, {"success": False, "message": "Patients can only verify their own records"})
                return
            if viewer["role"] == "doctor" and record.get("hospital_name") != viewer.get("hospital_name"):
                self.send_json(403, {"success": False, "message": "You can only verify records from your hospital"})
                return
            
            # Recalculate hash from CURRENT stored data
            recomputed_hash = calculate_ehr_hash(
                record["patient_id"],
                record["hospital_name"],
                record["diagnosis"],
                record["clinical_metrics"]
            )

            # Compare against the local in-memory ledger entry.
            bc_result = blockchain_ledger.verify_ehr_record(record_uuid, recomputed_hash)
            is_authentic = bc_result.get("is_valid", False)

            audit = {
                "id": len(AUDIT_LOGS) + 1,
                "record_uuid": record_uuid,
                "action": "VERIFICATION_CHECK",
                "status": "VERIFIED_AUTHENTIC" if is_authentic else "TAMPER_DETECTED",
                "timestamp": datetime.datetime.now().isoformat(),
                "details": f"Local ledger block #{bc_result.get('block_number')}: " + ("Hash matched" if is_authentic else "Hash mismatch; record contents differ from the sealed value")
            }
            AUDIT_LOGS.append(audit)

            self.send_json(200, {
                "success": True,
                "is_authentic": is_authentic,
                "status": "VERIFIED_AUTHENTIC" if is_authentic else "TAMPER_DETECTED",
                "record_uuid": record_uuid,
                "patient_name": record.get("patient_name", "Patient"),
                "hospital_name": record.get("hospital_name"),
                "diagnosis": record.get("diagnosis"),
                "blockchain_tx_hash": bc_result.get("tx_hash", record.get("blockchain_tx_hash")),
                "block_number": bc_result.get("block_number"),
                "stored_hash": bc_result.get("stored_hash", record["record_hash"]),
                "recomputed_hash": recomputed_hash,
                "created_at": record["created_at"],
                "blockchain_details": bc_result
            })
            return

        # DEMO TAMPERING ENDPOINT FOR VIVA EXAMINERS
        if path == "/api/demo/tamper-record":
            if not DEMO_TAMPER_ENABLED:
                self.send_json(404, {"success": False, "message": "Tamper demonstration is disabled"})
                return
            if not self.require_role("admin"):
                return
            record_uuid = body.get("record_uuid")
            if record_uuid in EHR_RECORDS_DB:
                EHR_RECORDS_DB[record_uuid]["diagnosis"] = "[TAMPERED DATA] Malicious Alteration Detected!"
                EHR_RECORDS_DB[record_uuid]["clinical_metrics"]["cholesterol"] = 999
                self.send_json(200, {
                    "success": True,
                    "message": f"Record {record_uuid} was intentionally modified in the database. Scan or verify now to watch tamper detection flag it in red!"
                })
                return
            self.send_json(404, {"success": False, "message": "Record not found"})
            return

        # ==========================================
        # 5. FEDERATED LEARNING TRIGGER (MODULE 2 & 3)
        # ==========================================
        if path == "/api/fl/trigger-round":
            if not self.require_role("admin"):
                return
            rounds = int(body.get("rounds", 3))
            epsilon = float(body.get("epsilon", 1.0))
            
            if HAS_FL_ENGINE:
                try:
                    results = run_federated_training(rounds=rounds, epsilon=epsilon)
                except ValueError as error:
                    self.send_json(400, {"success": False, "message": str(error)})
                    return
                except Exception as error:
                    print(f"[FL simulation error] {error}")
                    self.send_json(500, {"success": False, "message": "FL simulation failed; no result was recorded"})
                    return
                round_offset = FL_STATE["total_rounds"]
                for round_data in results["history"]:
                    global_round = round_offset + int(round_data["round"])
                    round_data["round"] = global_round

                    # Commit only DP-perturbed model hashes from virtual hospital edge nodes.
                    for update in round_data.get("node_updates", []):
                        receipt = blockchain_ledger.submit_fl_model_update(
                            global_round, update["update_hash"], update["hospital"]
                        )
                        update["ledger_tx_hash"] = receipt["tx_hash"]
                        update["ledger_block"] = receipt["block_number"]

                    receipt = blockchain_ledger.publish_global_fl_model(
                        global_round, round_data["global_model_hash"]
                    )
                    round_data["global_ledger_tx_hash"] = receipt["tx_hash"]
                    round_data["global_ledger_block"] = receipt["block_number"]
                    FL_STATE["history"].append(round_data)

                FL_STATE["total_rounds"] = round_offset + rounds
                FL_STATE["current_accuracy"] = results["final_accuracy"]
                FL_STATE["last_global_hash"] = results["final_global_hash"]
                FL_STATE["last_tx_hash"] = (
                    results["history"][-1].get("global_ledger_tx_hash")
                    if results["history"] else results["latest_tx_hash"]
                )

                self.send_json(200, {"success": True, "results": results})
            else:
                self.send_json(503, {"success": False, "message": "FL simulation dependencies are unavailable; no training result was generated."})
            return

        self.send_error(404, "Endpoint not found")

def run_server():
    server_address = ("127.0.0.1", PORT)
    httpd = socketserver.TCPServer(server_address, SecureHealthHandler)
    print("=" * 70)
    print(" [*] SECUREHEALTH CHAIN: PLATFORM SERVER RUNNING")
    print(f" [*] Access Web Application at: http://127.0.0.1:{PORT}")
    print(" [*] Default Logins:")
    print("     - Doctor:  doctor@securehealth.org  (Password: doctor)")
    print("     - Patient: patient@securehealth.org (Password: patient)")
    print("     - Admin:   admin@securehealth.org   (Password: admin)")
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server shutdown.")

if __name__ == "__main__":
    run_server()
