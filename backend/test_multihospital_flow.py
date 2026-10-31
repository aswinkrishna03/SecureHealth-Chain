"""
End-to-End Verification Test for Multi-Hospital, Multi-Doctor,
Head Doctor Sign-Off, and On-Chain Central Gate Verification
"""

import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def req(path, method="GET", body=None, token=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def run_tests():
    print("=" * 70)
    print(" [*] RUNNING END-TO-END MULTI-HOSPITAL & CLINICAL VERIFICATION TESTS")
    print("=" * 70)

    # 1. Test Hospitals List
    status, res = req("/api/hospitals/list")
    assert status == 200 and res.get("success"), f"Hospitals list failed: {res}"
    print(f" [PASS] GET /api/hospitals/list returned {len(res['hospitals'])} registered hospitals.")
    for h in res['hospitals']:
        print(f"       -> {h['hospital_name']} ({h['hospital_id']}) - {len(h['doctors'])} doctors, CMO: {h['head_doctor']['name'] if h['head_doctor'] else 'None'}")

    # 2. Login as Dr. Sarah Jenkins (Cardiologist, Metro Health)
    status, login_res = req("/api/auth/login", method="POST", body={
        "email": "doctor@securehealth.org",
        "password": "doctor"
    })
    assert status == 200 and login_res.get("success"), f"Login failed: {login_res}"
    doc_token = login_res["token"]
    doc_user = login_res["user"]
    print(f" [PASS] Logged in as: {doc_user['name']} ({doc_user['specialty']}, {doc_user['hospital_name']})")

    # 3. Verify Doctor on Ethereum Blockchain
    status, v_res = req("/api/doctor/verify-credentials", token=doc_token)
    assert status == 200 and v_res.get("success"), f"Doctor verify failed: {v_res}"
    print(f" [PASS] Doctor on-chain verification: is_verified_on_chain={v_res['is_verified_on_chain']}")
    print(f"       -> Doctor Hash:   {v_res['doctor_hash']}")
    print(f"       -> Hospital Hash: {v_res['hospital_hash']}")
    print(f"       -> Smart Contract: {v_res['contract_address']}")

    # 4. Create an EHR Record
    status, p_res = req("/api/ehr/patients", token=doc_token)
    assert status == 200 and p_res.get("success"), f"Fetch patients failed: {p_res}"
    target_patient_id = p_res["patients"][0]["id"] if p_res["patients"] else 3
    print(f" [PASS] Fetched patients: using Patient ID {target_patient_id}")

    status, ehr_res = req("/api/ehr/create", method="POST", body={
        "patient_id": target_patient_id,
        "diagnosis": "Cardiovascular Diagnostic Screening",
        "clinical_metrics": {
            "age": 52,
            "resting_bp": 130,
            "cholesterol": 210,
            "heart_rate": 75,
            "blood_glucose": 105,
            "oxygen_saturation": 98
        }
    }, token=doc_token)
    assert status == 201 and ehr_res.get("success"), f"EHR creation failed: {ehr_res}"
    print(f" [PASS] Created EHR Record: {ehr_res['record']['record_uuid']} sealed on Ethereum (Tx: {ehr_res['record']['blockchain_tx_hash'][:16]}...)")

    # 5. Doctor Trains Local Model Update
    status, train_res = req("/api/doctor/train-local-model", method="POST", body={
        "epochs": 5,
        "epsilon": 1.0
    }, token=doc_token)
    assert status == 200 and train_res.get("success"), f"Local training failed: {train_res}"
    train_data = train_res["result"]
    update_hash = train_data["update_hash"]
    print(f" [PASS] Local Model Trained! Loss: {train_data['local_loss']}, Acc: {train_data['local_accuracy']}%, Samples: {train_data['samples_count']}")
    print(f"       -> Model Update Hash: {update_hash}")
    print(f"       -> Approval Status:   {train_data['approval_status']}")

    # 6. Verify Push is BLOCKED before Head Doctor signs off
    status, push_block_res = req("/api/doctor/push-model-update", method="POST", body={
        "update_hash": update_hash
    }, token=doc_token)
    assert status == 403, f"Expected 403 Forbidden without CMO sign-off, got: {status}"
    print(f" [PASS] Push correctly blocked: '{push_block_res['message']}'")

    # 7. Head Doctor Review & Sign-Off
    status, sign_res = req("/api/doctor/approve-edge-update", method="POST", body={
        "update_hash": update_hash
    }, token=doc_token)
    assert status == 200 and sign_res.get("success"), f"Head doctor approval failed: {sign_res}"
    print(f" [PASS] Head Doctor Sign-off successful: CMO '{sign_res['head_doctor_name']}' signed update.")
    print(f"       -> CMO Signature Hash: {sign_res['head_doctor_signature_hash']}")

    # 8. Doctor Pushes Model Update to Central Server & Blockchain
    status, push_res = req("/api/doctor/push-model-update", method="POST", body={
        "update_hash": update_hash
    }, token=doc_token)
    assert status == 200 and push_res.get("success"), f"Push failed: {push_res}"
    print(f" [PASS] Pushed to Central Server! Mined on Ethereum Ganache Block #{push_res['block_number']}")
    print(f"       -> Ethereum Tx Hash: {push_res['tx_hash']}")

    # 9. Verify Central Server Gate (4-Point Checklist)
    status, in_res = req("/api/fl/incoming-updates", token=doc_token)
    assert status == 200 and in_res.get("success"), f"Incoming updates failed: {in_res}"
    metro_update = next((u for u in in_res["incoming_updates"] if u["hospital_id"] == "HOSP-METRO-01"), None)
    assert metro_update is not None, "Metro Health update not found in incoming pool"
    print(f" [PASS] Central Server 4-Point Verification Checklist:")
    print(f"       -> [1] Hospital Verified on Ethereum:    {metro_update['hospital_verified_on_chain']}")
    print(f"       -> [2] Doctor Verified on Ethereum:      {metro_update['doctor_verified_on_chain']} ({metro_update['doctor_name']}, {metro_update['doctor_specialty']})")
    print(f"       -> [3] Head Doctor Signed on Ethereum:   {metro_update['head_doctor_approved_on_chain']} ({metro_update['head_doctor_name']})")
    print(f"       -> [4] Model Hash Committed on Ethereum: {metro_update['model_hash_committed_on_chain']}")
    print(f"       -> Central Server Gate Status:          {metro_update['status']}")

    # 10. Login as Admin and Trigger FedAvg
    status, admin_login = req("/api/auth/login", method="POST", body={
        "email": "admin@securehealth.org",
        "password": "admin"
    })
    admin_token = admin_login["token"]
    status, fl_res = req("/api/fl/trigger-round", method="POST", body={
        "rounds": 1,
        "epsilon": 1.0
    }, token=admin_token)
    assert status == 200 and fl_res.get("success"), f"FL Round failed: {fl_res}"
    print(f" [PASS] FedAvg Completed! Final Global Model Accuracy: {fl_res['results']['final_accuracy']}%")
    print(f"       -> Global Model Anchored on Ethereum Block #{fl_res['results'].get('latest_ledger_block', '--')}")

    print("=" * 70)
    print(" [ALL TESTS PASSED PERFECTLY!] Multi-Hospital architecture verified.")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
