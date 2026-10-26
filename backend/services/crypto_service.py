import hashlib
import json

def calculate_ehr_hash(patient_id: int, hospital_name: str, diagnosis: str, clinical_metrics: dict) -> str:
    """
    Computes a deterministic cryptographic SHA-256 hash of an EHR record.
    Keys are sorted to guarantee canonical representation across platforms.
    """
    canonical_payload = {
        "patient_id": patient_id,
        "hospital_name": hospital_name.strip(),
        "diagnosis": diagnosis.strip(),
        "clinical_metrics": clinical_metrics
    }
    encoded_data = json.dumps(canonical_payload, sort_keys=True).encode('utf-8')
    return "0x" + hashlib.sha256(encoded_data).hexdigest()
