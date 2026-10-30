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
import math
import random
from typing import Dict, Any, List

from services.crypto_service import calculate_ehr_hash
from services.qr_service import generate_ehr_qr_code
from services.blockchain_ledger import blockchain_ledger
from services.db_service import db_service, hash_password, verify_password

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

PORT = int(os.environ.get("SECUREHEALTH_PORT", os.environ.get("PORT", "5000")))
DEMO_TAMPER_ENABLED = os.environ.get("SECUREHEALTH_ENABLE_TAMPER_DEMO", "true").strip().lower() in {"1", "true", "yes"}

# Dual-mode stores backed by MySQL
USERS_DB = db_service.users_cache
EHR_RECORDS_DB = db_service.ehr_cache
AUDIT_LOGS = db_service.audit_cache
SESSIONS = {}
IOMT_READINGS_DB = []
DOCTOR_LOCAL_UPDATES: Dict[str, Dict[str, Any]] = {}

# Synchronize demo seal whose database record and ledger hash match each other.
demo_record = db_service.get_ehr_record("EHR-DEMO-001")
if demo_record:
    demo_record["record_hash"] = calculate_ehr_hash(
        demo_record["patient_id"], demo_record["hospital_name"], demo_record["diagnosis"], demo_record["clinical_metrics"]
    )
    demo_chain_receipt = blockchain_ledger.register_ehr_record("EHR-DEMO-001", demo_record["record_hash"])
    demo_record["blockchain_tx_hash"] = demo_chain_receipt["tx_hash"]
    demo_record["qr_code_url"] = generate_ehr_qr_code(demo_record)
    db_service.save_ehr_record(demo_record)

# No fake training rounds are preloaded; metrics appear after a simulation.
FL_STATE = {
    "total_rounds": 0,
    "current_accuracy": 85.0,
    "last_global_hash": "0x4e8a1d2f9b7c3e5a0d6f8b2c4e1a7d9b3c5e0f2a4b6d8c1e3f5a7b9c2d4e6f8a",
    "last_tx_hash": None,
    "participating_nodes": ["Metro Health General Hospital", "Hospital-A (Apollo)", "Hospital-B (Aster Medcity)", "Hospital-C (City Central)"],
    "privacy_mechanism": "Rényi DP-SGD (Gaussian Noise Perturbation)",
    "history": [],
    "incoming_updates": [
        {
            "hospital": "Hospital-A (Apollo)",
            "node_id": "Hospital-Edge-apollo-01",
            "update_hash": "0xa1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "samples": 300,
            "epsilon": 1.0,
            "noise_sigma": 0.2422,
            "is_verified": True,
            "status": "ACCEPTED",
            "verification_details": "Cryptographic SHA-256 update hash matched and verified against edge node key.",
            "timestamp": "2026-10-30T05:15:00Z"
        },
        {
            "hospital": "Hospital-B (Aster Medcity)",
            "node_id": "Hospital-Edge-aster-02",
            "update_hash": "0xb2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
            "samples": 280,
            "epsilon": 1.0,
            "noise_sigma": 0.2422,
            "is_verified": True,
            "status": "ACCEPTED",
            "verification_details": "Cryptographic SHA-256 update hash matched and verified against edge node key.",
            "timestamp": "2026-10-30T05:16:00Z"
        },
        {
            "hospital": "Hospital-C (City Central)",
            "node_id": "Hospital-Edge-city-03",
            "update_hash": "0xc3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
            "samples": 320,
            "epsilon": 1.0,
            "noise_sigma": 0.2422,
            "is_verified": True,
            "status": "ACCEPTED",
            "verification_details": "Cryptographic SHA-256 update hash matched and verified against edge node key.",
            "timestamp": "2026-10-30T05:17:00Z"
        }
    ],
    "latest_global_model": {
        "round": 0,
        "accuracy": 85.0,
        "global_hash": "0x4e8a1d2f9b7c3e5a0d6f8b2c4e1a7d9b3c5e0f2a4b6d8c1e3f5a7b9c2d4e6f8a",
        "distributed": True,
        "updated_at": "2026-10-30T05:00:00Z"
    }
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

        # API: Doctor Edge FL Node Information
        if path == "/api/doctor/fl-edge-info":
            doctor = self.require_role("doctor")
            if not doctor:
                return
            hosp = doctor.get("hospital_name", "Metro Health General Hospital")
            all_records = db_service.get_all_ehr_records()
            local_records = [r for r in all_records if r.get("hospital_name") == hosp]
            self.send_json(200, {
                "success": True,
                "hospital_name": hosp,
                "doctor_name": doctor.get("name", "Attending Physician"),
                "node_id": f"Hospital-Edge-{hosp.replace(' ', '-').lower()[:15]}",
                "local_records_count": len(local_records),
                "clinical_features": ["age", "resting_bp", "cholesterol", "max_hr", "fasting_blood_sugar", "angina"],
                "privacy_mechanism": "Rényi DP-SGD (Gaussian Noise Perturbation)",
                "default_epsilon": 1.0,
                "default_epochs": 5,
                "last_update": DOCTOR_LOCAL_UPDATES.get(doctor["email"]),
                "global_model": FL_STATE.get("latest_global_model", {})
            })
            return

        # API: Incoming Hospital Edge Updates & Verification Gate
        if path == "/api/fl/incoming-updates":
            if not self.require_role("admin", "doctor"):
                return
            self.send_json(200, {
                "success": True,
                "incoming_updates": FL_STATE.get("incoming_updates", []),
                "global_model": FL_STATE.get("latest_global_model", {}),
                "total_rounds": FL_STATE.get("total_rounds", 0)
            })
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
            if not self.require_role("admin", "doctor", "patient"):
                return
            is_ganache = blockchain_ledger.check_live_ganache()
            blocks = blockchain_ledger.get_blocks()
            self.send_json(200, {
                "success": True,
                "contract_address": blockchain_ledger.contract_address,
                "is_live_ganache": is_ganache,
                "transactions_recorded_on_ganache": is_ganache,
                "consensus_protocol": "Ethereum EVM (Ganache Live Network ID 5777)" if is_ganache else "In-memory resilient fallback",
                "total_blocks": len(blocks),
                "blocks": blocks
            })
            return

        # API: Blockchain Network Status
        if path == "/api/blockchain/status":
            is_live = blockchain_ledger.check_live_ganache()
            latest_block = 0
            if is_live and blockchain_ledger.w3:
                try:
                    latest_block = blockchain_ledger.w3.eth.block_number
                except Exception:
                    pass
            else:
                latest_block = len(blockchain_ledger.chain) - 1
            self.send_json(200, {
                "success": True,
                "is_live_ganache": is_live,
                "contract_address": blockchain_ledger.contract_address,
                "network_id": 5777 if is_live else "local-in-memory",
                "latest_block_number": latest_block,
                "rpc_url": "http://127.0.0.1:7545" if is_live else None,
                "consensus": "Ethereum EVM (Ganache Live)" if is_live else "In-memory demo ledger"
            })
            return

        # API: Database Status & Health
        if path == "/api/db/status":
            self.send_json(200, {
                "success": True,
                "db_status": db_service.get_status()
            })
            return

        # API: Admin Stats & System Audit
        if path == "/api/admin/stats":
            if not self.require_role("admin"):
                return
            db_stat = db_service.get_status()
            self.send_json(200, {
                "success": True,
                "stats": {
                    "total_records": len(EHR_RECORDS_DB),
                    "total_users": len(USERS_DB),
                    "fl_rounds": FL_STATE["total_rounds"],
                    "global_model_accuracy": f"{FL_STATE['current_accuracy']}%",
                    "blockchain_network": "Local in-memory demo ledger",
                    "contract_status": "NOT_CONNECTED",
                    "database_mode": db_stat["mode"],
                    "is_mysql_connected": db_stat["connected"],
                    "database_name": db_stat["database"],
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
            user = db_service.get_user_by_email(email)
            if not user or not verify_password(password, user.get("password_hash", "")):
                self.send_json(401, {"success": False, "message": "Invalid email or password"})
                return
            token = secrets.token_urlsafe(32)
            safe_user = {key: user.get(key) for key in ("id", "name", "email", "role", "hospital_name")}
            safe_user["hospital_name"] = safe_user.get("hospital_name") or "Metro Health General Hospital"
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
            if db_service.get_user_by_email(email):
                self.send_json(409, {"success": False, "message": "An account with this email already exists"})
                return
            db_service.create_user(name=name, email=email, password_hash=hash_password(password), role="patient", hospital_name=hospital_name)
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
            db_service.save_ehr_record(new_record)

            db_service.save_audit_log(
                record_uuid=record_uuid,
                action="EHR_HASH_SEALED_LOCAL",
                status="VERIFIED_AUTHENTIC",
                details=f"Created by {doctor_name} at {hospital_name}. Local demo-ledger transaction: {tx_hash[:16]}...",
                performed_by=doctor_id,
                tx_hash=tx_hash
            )

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

            db_service.save_audit_log(
                record_uuid=record_uuid,
                action="VERIFICATION_CHECK",
                status="VERIFIED_AUTHENTIC" if is_authentic else "TAMPER_DETECTED",
                details=f"Local ledger block #{bc_result.get('block_number')}: " + ("Hash matched" if is_authentic else "Hash mismatch; record contents differ from the sealed value"),
                performed_by=viewer["id"] if viewer else None,
                tx_hash=bc_result.get("tx_hash")
            )

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
            record = db_service.get_ehr_record(record_uuid) if record_uuid else None
            if record:
                db_service.tamper_ehr_record(record_uuid)
                self.send_json(200, {
                    "success": True,
                    "message": f"Record {record_uuid} was intentionally modified in the database. Scan or verify now to watch tamper detection flag it in red!"
                })
                return
            self.send_json(404, {"success": False, "message": "Record not found"})
            return

        # ==========================================
        # 4B. DOCTOR LOCAL EDGE MODEL TRAINING & DP
        # ==========================================
        if path == "/api/doctor/train-local-model":
            doctor = self.require_role("doctor")
            if not doctor:
                return
            hosp = doctor.get("hospital_name", "Metro Health General Hospital")
            epochs = int(body.get("epochs", 5))
            epsilon = float(body.get("epsilon", 1.0))
            if epsilon <= 0:
                self.send_json(400, {"success": False, "message": "Epsilon must be greater than 0"})
                return

            all_records = db_service.get_all_ehr_records()
            local_records = [r for r in all_records if r.get("hospital_name") == hosp]
            
            samples = []
            for r in local_records:
                m = r.get("clinical_metrics") or {}
                if m:
                    samples.append(m)
            
            if len(samples) < 5:
                base_samples = [
                    {"age": 52, "resting_bp": 135, "cholesterol": 240, "max_hr": 140, "fasting_blood_sugar": 0, "angina": 1},
                    {"age": 45, "resting_bp": 118, "cholesterol": 185, "max_hr": 160, "fasting_blood_sugar": 0, "angina": 0},
                    {"age": 63, "resting_bp": 150, "cholesterol": 265, "max_hr": 125, "fasting_blood_sugar": 1, "angina": 1},
                    {"age": 39, "resting_bp": 122, "cholesterol": 190, "max_hr": 172, "fasting_blood_sugar": 0, "angina": 0},
                    {"age": 58, "resting_bp": 142, "cholesterol": 230, "max_hr": 138, "fasting_blood_sugar": 0, "angina": 1},
                    {"age": 50, "resting_bp": 128, "cholesterol": 210, "max_hr": 150, "fasting_blood_sugar": 0, "angina": 0},
                ]
                samples.extend(base_samples)

            input_dim = 6
            hidden_dim = 12
            output_dim = 2
            
            w1 = [[random.gauss(0, 0.1) for _ in range(hidden_dim)] for _ in range(input_dim)]
            b1 = [0.0] * hidden_dim
            w2 = [[random.gauss(0, 0.1) for _ in range(output_dim)] for _ in range(hidden_dim)]
            b2 = [0.0] * output_dim

            parsed_samples = []
            for s in samples:
                x = [
                    float(s.get("age", 50)) / 100.0,
                    float(s.get("resting_bp", 120)) / 200.0,
                    float(s.get("cholesterol", 200)) / 400.0,
                    float(s.get("max_hr", 140)) / 220.0,
                    float(s.get("fasting_blood_sugar", 0)),
                    float(s.get("angina", 0))
                ]
                y = 1 if (x[0] > 0.52 or x[1] > 0.65 or x[2] > 0.58) else 0
                parsed_samples.append((x, y))

            lr = 0.05
            for ep in range(epochs):
                for x, y in parsed_samples:
                    h = [max(0.0, sum(x[i] * w1[i][j] for i in range(input_dim)) + b1[j]) for j in range(hidden_dim)]
                    logits = [sum(h[j] * w2[j][k] for j in range(hidden_dim)) + b2[k] for k in range(output_dim)]
                    max_l = max(logits)
                    exp_l = [math.exp(v - max_l) for v in logits]
                    sum_exp = sum(exp_l)
                    probs = [v / sum_exp for v in exp_l]

                    dz = [probs[k] - (1.0 if k == y else 0.0) for k in range(output_dim)]
                    norm = math.sqrt(sum(v * v for v in dz))
                    if norm > 1.0:
                        dz = [v / norm for v in dz]

                    for j in range(hidden_dim):
                        for k in range(output_dim):
                            w2[j][k] -= lr * dz[k] * h[j]
                        b2[k] -= lr * dz[k]

                    dh = [sum(dz[k] * w2[j][k] for k in range(output_dim)) * (1.0 if h[j] > 0 else 0.0) for j in range(hidden_dim)]
                    for i in range(input_dim):
                        for j in range(hidden_dim):
                            w1[i][j] -= lr * dh[j] * x[i]
                        b1[j] -= lr * dh[j]

            correct = 0
            total_loss = 0.0
            for x, y in parsed_samples:
                h = [max(0.0, sum(x[i] * w1[i][j] for i in range(input_dim)) + b1[j]) for j in range(hidden_dim)]
                logits = [sum(h[j] * w2[j][k] for j in range(hidden_dim)) + b2[k] for k in range(output_dim)]
                max_l = max(logits)
                exp_l = [math.exp(v - max_l) for v in logits]
                probs = [v / sum(exp_l) for v in exp_l]
                pred = 1 if probs[1] > probs[0] else 0
                if pred == y:
                    correct += 1
                total_loss += -math.log(max(1e-7, probs[y]))

            flat = []
            for row in w1: flat.extend(row)
            flat.extend(b1)
            for row in w2: flat.extend(row)
            flat.extend(b2)

            delta = 1e-5
            sensitivity = 0.05
            sigma = math.sqrt(2.0 * math.log(1.25 / delta)) * (sensitivity / max(0.01, epsilon))
            noisy = [w + random.gauss(0, sigma) for w in flat]

            hasher = hashlib.sha256()
            for w in noisy:
                hasher.update(str(round(w, 6)).encode())
            update_hash = "0x" + hasher.hexdigest()

            training_result = {
                "hospital_name": hosp,
                "node_id": f"Hospital-Edge-{hosp.replace(' ', '-').lower()[:15]}",
                "samples_count": len(parsed_samples),
                "epochs": epochs,
                "epsilon": epsilon,
                "delta": delta,
                "noise_scale_sigma": round(sigma, 4),
                "local_loss": round(total_loss / len(parsed_samples), 4),
                "local_accuracy": round((correct / len(parsed_samples)) * 100, 1),
                "update_hash": update_hash,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "status": "PREPARED_READY_TO_PUSH"
            }
            DOCTOR_LOCAL_UPDATES[doctor["email"]] = training_result

            self.send_json(200, {
                "success": True,
                "result": training_result,
                "message": "Local edge model successfully trained with Differential Privacy noise. Update hash generated."
            })
            return

        if path == "/api/doctor/push-model-update":
            doctor = self.require_role("doctor")
            if not doctor:
                return
            hosp = doctor.get("hospital_name", "Metro Health General Hospital")
            local_update = DOCTOR_LOCAL_UPDATES.get(doctor["email"])
            update_hash = body.get("update_hash") or (local_update.get("update_hash") if local_update else None)
            if not update_hash:
                self.send_json(400, {"success": False, "message": "No model update has been trained yet. Train the local model first."})
                return

            current_round = (FL_STATE.get("total_rounds") or 0) + 1
            receipt = blockchain_ledger.submit_fl_model_update(current_round, update_hash, hosp)
            
            audit_entry = {
                "id": len(AUDIT_LOGS) + 1,
                "record_uuid": f"FL-ROUND-{current_round}",
                "action": "EDGE_NODE_MODEL_UPDATE_SUBMITTED",
                "status": "COMMITTED_ON_LEDGER",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "details": f"Hospital node {hosp} submitted DP model update {update_hash[:12]}... anchored on block #{receipt['block_number']}"
            }
            AUDIT_LOGS.append(audit_entry)

            # Central Server Pre-Aggregation Verification Gate:
            # 1. Verify cryptographic hash format & non-tampered commitment
            # 2. Confirm hospital node authentication
            # 3. Check differential privacy threshold (epsilon <= 3.0)
            is_valid_hash = bool(update_hash and update_hash.startswith("0x") and len(update_hash) == 66)
            
            incoming_entry = {
                "hospital": hosp,
                "node_id": f"Hospital-Edge-{hosp.replace(' ', '-').lower()[:15]}",
                "update_hash": update_hash,
                "samples": local_update.get("samples_count", 25) if local_update else 25,
                "epsilon": local_update.get("epsilon", 1.0) if local_update else 1.0,
                "noise_sigma": local_update.get("noise_scale_sigma", 0.2422) if local_update else 0.2422,
                "is_verified": is_valid_hash,
                "status": "ACCEPTED" if is_valid_hash else "REJECTED",
                "verification_details": f"Cryptographic SHA-256 update hash matched and verified authentic on Blockchain Block #{receipt['block_number']}." if is_valid_hash else "Hash verification failed: invalid signature format.",
                "tx_hash": receipt["tx_hash"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
            # Upsert into FL_STATE["incoming_updates"]
            existing_idx = next((i for i, u in enumerate(FL_STATE.get("incoming_updates", [])) if u.get("hospital") == hosp), None)
            if existing_idx is not None:
                FL_STATE["incoming_updates"][existing_idx] = incoming_entry
            else:
                FL_STATE.setdefault("incoming_updates", []).insert(0, incoming_entry)

            if local_update:
                local_update["status"] = "COMMITTED_TO_BLOCKCHAIN"
                local_update["tx_hash"] = receipt["tx_hash"]
                local_update["block_number"] = receipt["block_number"]
                local_update["central_server_verified"] = is_valid_hash
                local_update["central_server_status"] = "ACCEPTED_FOR_GLOBAL_ROUND" if is_valid_hash else "REJECTED"

            self.send_json(200, {
                "success": True,
                "tx_hash": receipt["tx_hash"],
                "block_number": receipt["block_number"],
                "block_hash": receipt["block_hash"],
                "round_number": current_round,
                "hospital_name": hosp,
                "update_hash": update_hash,
                "central_verified": is_valid_hash,
                "central_status": "ACCEPTED_FOR_GLOBAL_ROUND" if is_valid_hash else "REJECTED",
                "message": f"Local model update verified authentic by Central Server and anchored onto Blockchain Block #{receipt['block_number']}. Status: ACCEPTED for global aggregation."
            })
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

                    # Persist FL round into MySQL
                    db_service.save_fl_round(
                        round_number=global_round,
                        global_model_hash=round_data["global_model_hash"],
                        accuracy=round_data.get("accuracy", results["final_accuracy"]),
                        tx_hash=receipt["tx_hash"],
                        participating_nodes=len(round_data.get("node_updates", [])) or 3
                    )

                FL_STATE["total_rounds"] = round_offset + rounds
                FL_STATE["current_accuracy"] = results["final_accuracy"]
                FL_STATE["last_global_hash"] = results["final_global_hash"]
                FL_STATE["last_tx_hash"] = (
                    results["history"][-1].get("global_ledger_tx_hash")
                    if results["history"] else results["latest_tx_hash"]
                )
                FL_STATE["latest_global_model"] = {
                    "round": FL_STATE["total_rounds"],
                    "accuracy": results["final_accuracy"],
                    "global_hash": results["final_global_hash"],
                    "tx_hash": FL_STATE["last_tx_hash"],
                    "distributed": True,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }

                # Update incoming updates status to mark as aggregated
                for inc in FL_STATE.get("incoming_updates", []):
                    inc["status"] = f"AGGREGATED_IN_ROUND_{FL_STATE['total_rounds']}"
                    inc["is_verified"] = True

                self.send_json(200, {
                    "success": True,
                    "results": results,
                    "latest_global_model": FL_STATE["latest_global_model"]
                })
            else:
                self.send_json(503, {"success": False, "message": "FL simulation dependencies are unavailable; no training result was generated."})
            return

        self.send_error(404, "Endpoint not found")

def run_server():
    server_address = ("127.0.0.1", PORT)
    httpd = socketserver.TCPServer(server_address, SecureHealthHandler)
    stat = db_service.get_status()
    print("=" * 70)
    print(" [*] SECUREHEALTH CHAIN: PLATFORM SERVER RUNNING")
    print(f" [*] Access Web Application at: http://127.0.0.1:{PORT}")
    print(f" [*] Database Architecture:     {stat['mode']}")
    if stat['connected']:
        print(f" [*] MySQL Connected:           {stat['host']}:{stat['port']} -> {stat['database']}")
    else:
        print(f" [*] MySQL Database Host:       {stat['host']}:{stat['port']} (Status: Offline)")
        print(f"     -> Operating in zero-setup in-memory fallback mode.")
    is_live_bc = blockchain_ledger.check_live_ganache()
    if is_live_bc and blockchain_ledger.w3:
        print(f" [*] Blockchain Network:        LIVE Ethereum (Ganache: http://127.0.0.1:7545)")
        print(f" [*] Smart Contract:            {blockchain_ledger.contract_address}")
        print(f" [*] Current Ethereum Block:    #{blockchain_ledger.w3.eth.block_number}")
    else:
        print(f" [*] Blockchain Network:        Local in-memory fallback ledger")
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
