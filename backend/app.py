"""
SecureHealth Chain - Flask Backend Entry Point
REST API providing:
- Role-based Authentication (Admin, Doctor, Patient)
- Electronic Health Record (EHR) registration & SHA-256 hashing
- Ethereum Ganache Smart Contract integration
- AI Health Risk Prediction
- QR Code generation & instant verification
"""

import os
import uuid
import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from services.crypto_service import calculate_ehr_hash
from services.blockchain_service import blockchain_service
from services.qr_service import generate_ehr_qr_code

app = Flask(__name__)
CORS(app)

# In-Memory stores for lightweight demonstration (can be linked to MySQL)
USERS_DB = {
    "admin@securehealth.org": {
        "id": 1,
        "name": "System Administrator",
        "email": "admin@securehealth.org",
        "password_hash": generate_password_hash("admin123"),
        "role": "admin",
        "hospital_name": "Health Network HQ"
    },
    "doctor@securehealth.org": {
        "id": 2,
        "name": "Dr. Sarah Jenkins",
        "email": "doctor@securehealth.org",
        "password_hash": generate_password_hash("doctor123"),
        "role": "doctor",
        "hospital_name": "Metro Health General Hospital"
    },
    "patient@securehealth.org": {
        "id": 3,
        "name": "Aswin Krishna",
        "email": "patient@securehealth.org",
        "password_hash": generate_password_hash("patient123"),
        "role": "patient",
        "hospital_name": "Metro Health General Hospital"
    }
}

EHR_RECORDS_DB = {}
VERIFICATION_AUDIT_LOGS = []

# Serve QR Code images
@app.route('/static/qrcodes/<path:filename>')
def serve_qr(filename):
    return send_from_directory('static/qrcodes', filename)

# ==========================================
# MODULE 1: AUTHENTICATION & ROLE MANAGEMENT
# ==========================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = USERS_DB.get(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"success": False, "message": "Invalid email or password"}), 401

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "hospital_name": user["hospital_name"]
        },
        "token": f"jwt-mock-token-for-{user['role']}"
    }), 200

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    role = data.get("role", "patient").strip().lower()
    password = data.get("password", "")
    hospital_name = data.get("hospital_name", "Metro Health General Hospital")

    if email in USERS_DB:
        return jsonify({"success": False, "message": "User already exists"}), 400

    new_id = len(USERS_DB) + 1
    USERS_DB[email] = {
        "id": new_id,
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": role,
        "hospital_name": hospital_name
    }

    return jsonify({"success": True, "message": "User registered successfully", "id": new_id}), 201

# ==========================================
# MODULE 2 & 4: AI DISEASE RISK PREDICTION
# ==========================================

@app.route('/api/ai/predict-risk', methods=['POST'])
def predict_disease_risk():
    """
    Evaluates patient clinical vitals and returns disease probability score
    Features: age, sex, resting_bp, cholesterol, blood_sugar, max_hr, angina, etc.
    """
    data = request.get_json() or {}
    age = float(data.get("age", 45))
    cholesterol = float(data.get("cholesterol", 200))
    resting_bp = float(data.get("resting_bp", 120))
    max_hr = float(data.get("max_hr", 150))
    angina = int(data.get("angina", 0))

    # Lightweight clinical heuristic / model calculation
    risk_score = 0.15
    if age > 50: risk_score += 0.20
    if cholesterol > 240: risk_score += 0.25
    if resting_bp > 140: risk_score += 0.20
    if max_hr < 120: risk_score += 0.10
    if angina == 1: risk_score += 0.15

    risk_score = min(max(risk_score, 0.05), 0.98)
    risk_level = "High Risk" if risk_score >= 0.65 else ("Moderate Risk" if risk_score >= 0.40 else "Low Risk")

    return jsonify({
        "success": True,
        "risk_probability": round(risk_score * 100, 1),
        "risk_level": risk_level,
        "recommendations": [
            "Maintain regular lipid profile monitoring",
            "Follow structured aerobic exercise regimen",
            "Consult supervising cardiologist for confirmation"
        ]
    }), 200

# ==========================================
# MODULE 3: EHR CREATION, HASHING & BLOCKCHAIN
# ==========================================

@app.route('/api/ehr/create', methods=['POST'])
def create_ehr():
    data = request.get_json() or {}
    patient_id = int(data.get("patient_id", 3))
    doctor_id = int(data.get("doctor_id", 2))
    hospital_name = data.get("hospital_name", "Metro Health General Hospital")
    diagnosis = data.get("diagnosis", "Normal Health Checkup")
    clinical_metrics = data.get("clinical_metrics", {})

    record_uuid = f"EHR-{str(uuid.uuid4())[:8].upper()}"

    # 1. Compute Deterministic SHA-256 Hash
    record_hash = calculate_ehr_hash(patient_id, hospital_name, diagnosis, clinical_metrics)

    # 2. Register Hash on Ethereum Ganache Blockchain
    bc_result = blockchain_service.register_ehr(record_uuid, record_hash)
    blockchain_tx = bc_result.get("tx_hash")

    # 3. Generate Secure QR Code
    record_payload = {
        "record_uuid": record_uuid,
        "patient_id": patient_id,
        "record_hash": record_hash,
        "blockchain_tx_hash": blockchain_tx
    }
    qr_url = generate_ehr_qr_code(record_payload)

    # 4. Save Record
    EHR_RECORDS_DB[record_uuid] = {
        "record_uuid": record_uuid,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "hospital_name": hospital_name,
        "diagnosis": diagnosis,
        "clinical_metrics": clinical_metrics,
        "record_hash": record_hash,
        "blockchain_tx_hash": blockchain_tx,
        "qr_code_url": qr_url,
        "created_at": datetime.datetime.now().isoformat()
    }

    return jsonify({
        "success": True,
        "message": "EHR sealed on Ethereum blockchain" if bc_result.get("mode") == "live_blockchain" else "EHR sealed in the in-memory demo ledger",
        "ledger_mode": bc_result.get("mode"),
        "record": EHR_RECORDS_DB[record_uuid]
    }), 201

@app.route('/api/ehr/list', methods=['GET'])
def list_ehrs():
    patient_id = request.args.get("patient_id")
    records = list(EHR_RECORDS_DB.values())
    if patient_id:
        records = [r for r in records if str(r["patient_id"]) == str(patient_id)]
    return jsonify({"success": True, "records": records}), 200

# ==========================================
# MODULE 4: QR SCAN & INTEGRITY VERIFICATION
# ==========================================

@app.route('/api/verify/record', methods=['POST'])
def verify_record():
    """
    Validates whether an EHR record matches its immutable Ganache blockchain entry.
    Detects any unauthorized tampering or database alteration.
    """
    data = request.get_json() or {}
    record_uuid = data.get("record_uuid")
    
    if not record_uuid or record_uuid not in EHR_RECORDS_DB:
        return jsonify({"success": False, "message": "Record not found in system"}), 404

    record = EHR_RECORDS_DB[record_uuid]
    
    # Recalculate current hash from stored clinical contents
    current_recomputed_hash = calculate_ehr_hash(
        record["patient_id"],
        record["hospital_name"],
        record["diagnosis"],
        record["clinical_metrics"]
    )

    # Query Ethereum Ganache Smart Contract
    is_valid, recorded_by, timestamp = blockchain_service.verify_ehr(record_uuid, current_recomputed_hash)
    
    tampered = (not is_valid) or (current_recomputed_hash != record["record_hash"])

    audit_entry = {
        "record_uuid": record_uuid,
        "status": "TAMPER_DETECTED" if tampered else "VERIFIED_AUTHENTIC",
        "verified_at": datetime.datetime.now().isoformat(),
        "blockchain_tx": record.get("blockchain_tx_hash"),
        "tampered": tampered
    }
    VERIFICATION_AUDIT_LOGS.append(audit_entry)

    return jsonify({
        "success": True,
        "is_authentic": not tampered,
        "status": "TAMPER_DETECTED" if tampered else "VERIFIED_AUTHENTIC",
        "record_uuid": record_uuid,
        "on_chain_hash": record["record_hash"],
        "recomputed_hash": current_recomputed_hash,
        "blockchain_tx": record.get("blockchain_tx_hash"),
        "timestamp": timestamp or record["created_at"],
        "audit_logs": audit_entry
    }), 200

# Endpoint to simulate record tampering for final-year project demonstration
@app.route('/api/demo/tamper-record', methods=['POST'])
def demo_tamper():
    data = request.get_json() or {}
    record_uuid = data.get("record_uuid")
    if record_uuid in EHR_RECORDS_DB:
        # Alter clinical diagnosis in database without updating blockchain
        EHR_RECORDS_DB[record_uuid]["diagnosis"] = "ALTERED: Critical Heart Failure (Tampered Record)"
        return jsonify({"success": True, "message": f"Record {record_uuid} was intentionally tampered in database for demonstration."}), 200
    return jsonify({"success": False, "message": "Record not found"}), 404

if __name__ == "__main__":
    print("=" * 60)
    print(" [*] SecureHealth Chain Flask REST Server Starting...")
    print(" [*] Ganache Blockchain Connector Initialized")
    print(" [*] Ready to accept requests on http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
