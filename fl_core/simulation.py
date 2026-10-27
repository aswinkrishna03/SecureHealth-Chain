"""Local EPP-BCFL-style training demo with DP-SGD and CKKS-encrypted FedAvg.

This is a single-process educational simulation, not a live hospital network.
The RDP report covers training updates for one invocation; exact evaluation
metrics, public sample counts, and repeated invocations are outside that bound.
"""

import csv
import datetime
import hashlib
import io
import json
import os
import random
import zipfile
from typing import Any, Dict

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset", "heart_disease.csv")
SYNTHEA_ZIP_PATH = os.environ.get(
    "SYNTHEA_DATA_ZIP",
    os.path.join(os.path.expanduser("~"), "Downloads", "synthea_sample_data_csv_latest.zip"),
)
SAVED_MODEL_PATH = os.path.join(os.path.dirname(__file__), "global_disease_model.json")
HEART_FEATURES = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal"]
SYNTHEA_FEATURES = ["age", "sex", "bmi", "systolic_bp", "diastolic_bp", "glucose", "hba1c", "cholesterol", "heart_rate"]
DP_DELTA = 1e-5
DP_CLIP_NORM = 1.0
DP_LEARNING_RATE = 0.1
LOCAL_STEPS = 10
CKKS_POLY_MODULUS_DEGREE = 8192
CKKS_COEFF_MOD_BIT_SIZES = [60, 40, 40, 60]
CKKS_GLOBAL_SCALE = 2 ** 40
RDP_ORDERS = np.unique(np.concatenate((np.arange(1.25, 10.0, 0.25), np.arange(10.0, 257.0), [384.0, 512.0, 768.0, 1024.0])))
RAW_RANGES = {
    "age": (18, 120), "sex": (0, 1), "cp": (0, 3), "trestbps": (50, 260),
    "chol": (50, 700), "fbs": (0, 1), "restecg": (0, 2), "thalach": (30, 250),
    "exang": (0, 1), "oldpeak": (0, 10), "slope": (0, 2), "ca": (0, 4), "thal": (0, 3),
    "target": (0, 1),
}


def _load_heart_silos():
    silos = {}
    rejected_rows = 0
    with open(DATASET_PATH, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            try:
                values = {key: float(row[key]) for key in RAW_RANGES}
                valid = all(
                    np.isfinite(value) and RAW_RANGES[key][0] <= value <= RAW_RANGES[key][1]
                    for key, value in values.items()
                )
                integer_fields = ["sex", "cp", "fbs", "restecg", "exang", "slope", "ca", "thal", "target"]
                valid = valid and all(values[key].is_integer() for key in integer_fields)
                if not valid:
                    rejected_rows += 1
                    continue
                name = row.get("hospital_id") or "Hospital-A"
                features = [
                    values["age"] / 100.0, values["sex"], values["cp"] / 3.0,
                    values["trestbps"] / 200.0, values["chol"] / 400.0,
                    values["fbs"], values["restecg"] / 2.0,
                    values["thalach"] / 220.0, values["exang"],
                    values["oldpeak"] / 6.0, values["slope"] / 2.0,
                    values["ca"] / 3.0, values["thal"] / 3.0,
                ]
                silos.setdefault(name, []).append((features, int(values["target"])))
            except (KeyError, TypeError, ValueError):
                rejected_rows += 1
    if not silos:
        raise ValueError("The heart disease dataset is empty")
    return silos, rejected_rows, HEART_FEATURES, "bundled heart-disease sample"


def _load_synthea_silos(zip_path):
    """Build patient-level diabetes-risk rows from only the needed Synthea columns.

    The source archive is read in place; identifiers and raw tables are never copied
    into this repository. Edge-node membership is a deterministic demo partition.
    """
    with zipfile.ZipFile(zip_path) as archive:
        entries = {os.path.basename(item.filename).lower(): item for item in archive.infolist()}
        required = ("patients.csv", "conditions.csv", "observations.csv")
        missing = [name for name in required if name not in entries]
        if missing:
            raise ValueError("Synthea ZIP is missing required files: " + ", ".join(missing))

        selected_columns = {
            "patients.csv": ("Id", "BIRTHDATE", "GENDER"),
            "conditions.csv": ("PATIENT", "DESCRIPTION"),
            "observations.csv": ("DATE", "PATIENT", "DESCRIPTION", "VALUE"),
        }

        def read_rows(filename):
            with archive.open(entries[filename]) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                return [
                    {column: row.get(column, "") for column in selected_columns[filename]}
                    for row in reader
                ]

        patients = read_rows("patients.csv")
        conditions = read_rows("conditions.csv")
        observations = read_rows("observations.csv")

    feature_names = SYNTHEA_FEATURES
    patient_features = {}
    latest_dates = {}
    for row in patients:
        patient_id = row.get("Id", "").strip()
        if not patient_id:
            continue
        try:
            birth_date = datetime.date.fromisoformat(row["BIRTHDATE"][:10])
            age = (datetime.date.today() - birth_date).days / 365.2425
        except (KeyError, TypeError, ValueError):
            continue
        gender = row.get("GENDER", "").strip().upper()
        if not 0 <= age <= 120 or gender not in ("M", "F"):
            continue
        patient_features[patient_id] = {
            "age": age / 100.0,
            "sex": 1.0 if gender == "M" else 0.0,
        }
        latest_dates[patient_id] = {}

    description_to_feature = {
        "body mass index (bmi) [ratio]": "bmi",
        "systolic blood pressure": "systolic_bp",
        "diastolic blood pressure": "diastolic_bp",
        "glucose [mass/volume] in blood": "glucose",
        "glucose [mass/volume] in serum or plasma": "glucose",
        "hemoglobin a1c/hemoglobin.total in blood": "hba1c",
        "cholesterol [mass/volume] in serum or plasma": "cholesterol",
        "heart rate": "heart_rate",
    }
    scales = {
        "bmi": 60.0, "systolic_bp": 250.0, "diastolic_bp": 150.0,
        "glucose": 600.0, "hba1c": 20.0, "cholesterol": 600.0,
        "heart_rate": 250.0,
    }
    valid_ranges = {
        "bmi": (10, 100), "systolic_bp": (40, 300), "diastolic_bp": (20, 200),
        "glucose": (10, 1500), "hba1c": (2, 25), "cholesterol": (30, 1500),
        "heart_rate": (20, 250),
    }
    rejected_rows = 0
    for row in observations:
        patient_id = row.get("PATIENT", "").strip()
        feature = description_to_feature.get(row.get("DESCRIPTION", "").strip().lower())
        if patient_id not in patient_features or not feature:
            continue
        try:
            value = float(row.get("VALUE", ""))
            observed = datetime.date.fromisoformat(row.get("DATE", "")[:10])
        except (TypeError, ValueError):
            rejected_rows += 1
            continue
        if not np.isfinite(value):
            rejected_rows += 1
            continue
        lower, upper = valid_ranges[feature]
        if not lower <= value <= upper:
            rejected_rows += 1
            continue
        current_date = latest_dates[patient_id].get(feature)
        if current_date is None or observed >= current_date:
            patient_features[patient_id][feature] = value / scales[feature]
            latest_dates[patient_id][feature] = observed

    diabetic_patients = set()
    for row in conditions:
        description = row.get("DESCRIPTION", "").strip().lower()
        if "diabetes" in description or "prediabetes" in description:
            patient_id = row.get("PATIENT", "").strip()
            if patient_id in patient_features:
                diabetic_patients.add(patient_id)

    if len(diabetic_patients) < 4 or len(patient_features) < 12:
        raise ValueError("Synthea sample is too small for a meaningful local training demonstration")

    medians = {}
    for name in feature_names:
        available = [values[name] for values in patient_features.values() if name in values]
        medians[name] = float(np.median(available)) if available else 0.0

    silos = {}
    # Three reproducible virtual edge partitions simulate separate local sites;
    # they are not Synthea hospital identities or independent real institutions.
    for patient_id, values in patient_features.items():
        node_number = int(hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:8], 16) % 3
        node_name = f"Synthea Edge Node {node_number + 1}"
        features = [values.get(name, medians[name]) for name in feature_names]
        label = int(patient_id in diabetic_patients)
        silos.setdefault(node_name, []).append((features, label))

    positives = sum(label for rows in silos.values() for _, label in rows)
    negatives = sum(len(rows) for rows in silos.values()) - positives
    if positives < 4 or negatives < 4:
        raise ValueError("Synthea sample needs at least four positive and four negative patients")
    return silos, rejected_rows, feature_names, "Synthea synthetic EHR (diabetes/prediabetes label)"


def load_silos():
    if os.path.isfile(SYNTHEA_ZIP_PATH):
        return _load_synthea_silos(SYNTHEA_ZIP_PATH)
    return _load_heart_silos()


def _epsilon_from_gaussian_rdp(noise_multiplier, steps, delta=DP_DELTA):
    """Conservative RDP-to-(epsilon, delta) bound for full-batch Gaussian steps."""
    if noise_multiplier <= 0 or steps <= 0 or not 0 < delta < 1:
        raise ValueError("Invalid Gaussian accountant parameters")
    rdp = steps * RDP_ORDERS / (2.0 * noise_multiplier ** 2)
    epsilon_values = rdp + np.log(1.0 / delta) / (RDP_ORDERS - 1.0)
    return float(np.min(epsilon_values))


def _calibrate_noise_multiplier(target_epsilon, steps, delta=DP_DELTA):
    """Choose a Gaussian noise multiplier meeting the requested RDP bound."""
    low, high = 1e-4, 1.0
    while _epsilon_from_gaussian_rdp(high, steps, delta) > target_epsilon:
        high *= 2.0
        if high > 1e6:
            raise ValueError("Could not calibrate Gaussian noise for this privacy budget")
    for _ in range(80):
        middle = (low + high) / 2.0
        if _epsilon_from_gaussian_rdp(middle, steps, delta) > target_epsilon:
            low = middle
        else:
            high = middle
    return high


def _clip_and_average_per_example_gradients(x, y, parameters, clip_norm):
    """Compute a mean logistic-loss gradient after clipping each patient's L2 norm."""
    coef, intercept = parameters[:-1], parameters[-1]
    probabilities = 1.0 / (1.0 + np.exp(-np.clip(x @ coef + intercept, -30, 30)))
    errors = probabilities - y
    per_example = np.column_stack((errors[:, None] * x, errors))
    norms = np.linalg.norm(per_example, axis=1)
    clip_scales = np.minimum(1.0, clip_norm / np.maximum(norms, 1e-12))
    clipped_mean = np.sum(per_example * clip_scales[:, None], axis=0) / len(y)
    # This regularizer is deterministic post-processing of the current parameters.
    clipped_mean[:-1] += 0.001 * coef
    return clipped_mean


def _homomorphic_weighted_average(encrypted_updates, total_samples):
    """Compute sample-weighted FedAvg using encrypted CKKS vectors."""
    if not encrypted_updates or total_samples <= 0:
        raise ValueError("No encrypted client updates to aggregate")
    encrypted_average = None
    for item in encrypted_updates:
        weight = item["samples"] / total_samples
        weighted_ciphertext = item["encrypted_parameters"] * float(weight)
        encrypted_average = weighted_ciphertext if encrypted_average is None else encrypted_average + weighted_ciphertext
    return encrypted_average


def run_federated_training(rounds: int = 3, epsilon: float = 1.0) -> Dict[str, Any]:
    if not isinstance(rounds, int) or not 1 <= rounds <= 20:
        raise ValueError("rounds must be between 1 and 20")
    if not 0.1 <= float(epsilon) <= 10:
        raise ValueError("epsilon must be between 0.1 and 10")

    try:
        import tenseal as ts
    except ImportError as error:
        raise ValueError("Homomorphic aggregation requires TenSEAL; install backend requirements first") from error

    rng = random.SystemRandom()
    silos, rejected_rows, feature_names, dataset_name = load_silos()
    clients = {}
    local_validation = {}
    test_features, test_labels = [], []
    for hospital, rows in silos.items():
        x = np.asarray([row[0] for row in rows], dtype=float)
        y = np.asarray([row[1] for row in rows], dtype=int)
        stratify = y if len(np.unique(y)) == 2 and min(np.bincount(y)) >= 2 else None
        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.2, random_state=42, stratify=stratify
        )
        if len(np.unique(y_train)) < 2:
            continue
        clients[hospital] = (x_train, y_train)
        local_validation[hospital] = (x_test, y_test)
        test_features.extend(x_test.tolist())
        test_labels.extend(y_test.tolist())
    if not clients or not test_features:
        raise ValueError("Not enough labeled data to run the local FL simulation")

    total_dp_steps = rounds * LOCAL_STEPS
    noise_multiplier = _calibrate_noise_multiplier(float(epsilon), total_dp_steps, DP_DELTA)
    achieved_epsilon = _epsilon_from_gaussian_rdp(noise_multiplier, total_dp_steps, DP_DELTA)
    # The demo context is ephemeral. Clients receive only a public context;
    # production key custody must run outside this process or use threshold HE.
    secret_context = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=CKKS_POLY_MODULUS_DEGREE,
        coeff_mod_bit_sizes=CKKS_COEFF_MOD_BIT_SIZES,
    )
    secret_context.global_scale = CKKS_GLOBAL_SCALE
    public_context = secret_context.copy()
    public_context.make_context_public()
    global_coef = np.zeros(len(feature_names), dtype=float)
    global_intercept = 0.0
    history = []
    for server_round in range(1, rounds + 1):
        pending_updates = []
        for hospital, (x_train, y_train) in clients.items():
            # Paper p. 8 local update with per-example clipping and calibrated
            # Gaussian noise. The noise is applied to each full-batch update.
            local_parameters = np.append(global_coef.copy(), global_intercept)
            for _ in range(LOCAL_STEPS):
                mean_gradient = _clip_and_average_per_example_gradients(
                    x_train, y_train, local_parameters, DP_CLIP_NORM
                )
                # Replacement-adjacency sensitivity of a mean of clipped
                # per-patient gradients is bounded by 2*C/N.
                update_noise_std = DP_LEARNING_RATE * noise_multiplier * (2.0 * DP_CLIP_NORM / len(y_train))
                noise = np.asarray([rng.gauss(0, update_noise_std) for _ in local_parameters])
                local_parameters = local_parameters - DP_LEARNING_RATE * mean_gradient + noise
            coef, intercept = local_parameters[:-1], float(local_parameters[-1])
            x_valid, y_valid = local_validation[hospital]
            local_predictions = ((x_valid @ coef + intercept) >= 0).astype(int)
            local_accuracy = float(accuracy_score(y_valid, local_predictions))
            update_hash = "0x" + hashlib.sha256(local_parameters.tobytes()).hexdigest()
            pending_updates.append({
                "hospital": hospital,
                "encrypted_parameters": ts.ckks_vector(public_context, local_parameters.tolist()),
                "update_hash": update_hash,
                "samples": len(y_train),
                "local_accuracy": local_accuracy,
            })

        # Paper p. 8 FedAvg: perform weighted vector sum while encrypted, then
        # let the local key custodian decrypt only the global average.
        total_samples = sum(item["samples"] for item in pending_updates)
        encrypted_average = _homomorphic_weighted_average(pending_updates, total_samples)
        global_parameters = np.asarray(
            encrypted_average.decrypt(secret_context.secret_key()), dtype=float
        )
        global_coef = global_parameters[:-1]
        global_intercept = float(global_parameters[-1])
        node_updates = []
        for item in pending_updates:
            node_updates.append({
                "hospital": item["hospital"], "samples": item["samples"],
                "local_accuracy": round(item["local_accuracy"] * 100, 2),
                "update_hash": item["update_hash"],
            })

        x_eval = np.asarray(test_features, dtype=float)
        y_eval = np.asarray(test_labels, dtype=int)
        predictions = ((x_eval @ global_coef + global_intercept) >= 0).astype(int)
        accuracy = round(float(accuracy_score(y_eval, predictions)) * 100, 2)
        global_hash = "0x" + hashlib.sha256(np.append(global_coef, global_intercept).tobytes()).hexdigest()
        local_tx = "0x" + hashlib.sha256(f"local-demo-round-{server_round}-{global_hash}".encode()).hexdigest()
        history.append({
            "round": server_round,
            "accuracy": accuracy,
            "precision": round(float(precision_score(y_eval, predictions, zero_division=0)) * 100, 2),
            "recall": round(float(recall_score(y_eval, predictions, zero_division=0)) * 100, 2),
            "f1_score": round(float(f1_score(y_eval, predictions, zero_division=0)) * 100, 2),
            "global_model_hash": global_hash,
            "blockchain_tx": local_tx,
            "participating_nodes": len(node_updates),
            "node_updates": node_updates,
            "aggregation": "CKKS-encrypted sample-count weighted FedAvg (paper equation)",
            "rejected_edge_rows": rejected_rows,
        })

    final = history[-1]
    privacy_accounting = {
        "target_epsilon": float(epsilon), "achieved_epsilon_bound": achieved_epsilon,
        "delta": DP_DELTA, "noise_multiplier": noise_multiplier,
        "clipping_norm": DP_CLIP_NORM, "steps_per_client": total_dp_steps,
        "accounting": "full-batch Gaussian mechanism composed with RDP; public node sizes assumed",
        "scope": "training model updates only; exact evaluation metrics and repeated API invocations are not included",
    }
    he_scheme = "CKKS approximate homomorphic encryption (TenSEAL/Microsoft SEAL)"
    with open(SAVED_MODEL_PATH, "w", encoding="utf-8") as output:
        json.dump({"model": "sample-weighted logistic regression", "features": feature_names,
                   "coefficients": global_coef.tolist(), "intercept": global_intercept,
                   "held_out_accuracy": final["accuracy"], "simulation_only": True,
                   "dataset": dataset_name, "privacy_accounting": privacy_accounting,
                   "homomorphic_encryption": he_scheme,
                   "aggregation": "sample-count weighted FedAvg"}, output, indent=2)
    return {
        "success": True,
        "simulation": True,
        "dataset": dataset_name,
        "dataset_summary": {
            "patient_count": sum(len(rows) for rows in silos.values()),
            "edge_node_count": len(clients),
            "features": feature_names,
            "target": "recorded diabetes/prediabetes status" if dataset_name.startswith("Synthea") else "heart-disease sample target",
        },
        "total_rounds": rounds,
        "final_accuracy": final["accuracy"],
        "final_global_hash": final["global_model_hash"],
        "latest_tx_hash": final["blockchain_tx"],
        "privacy_note": f"DP-SGD per-sample clipping (C={DP_CLIP_NORM:g}), noise multiplier={noise_multiplier:.4g}; RDP epsilon<={achieved_epsilon:.4g}, delta={DP_DELTA:g} per invocation (separate runs compose); exact metrics are not DP",
        "homomorphic_encryption_note": "CKKS approximate HE: clients encrypt model vectors; coordinator computes weighted sum on ciphertext; only global average is decrypted by an in-process key custodian",
        "aggregation_note": "Paper FedAvg equation: CKKS ciphertext vectors are weighted by public local training counts and added before aggregate decryption",
        "privacy_accounting": privacy_accounting,
        "he_scheme": he_scheme,
        "he_parameters": {
            "poly_modulus_degree": CKKS_POLY_MODULUS_DEGREE,
            "coefficient_modulus_bits": CKKS_COEFF_MOD_BIT_SIZES,
            "global_scale": CKKS_GLOBAL_SCALE,
            "key_custody": "ephemeral key in the same process for this local demo",
        },
        "rejected_edge_rows": rejected_rows,
        "history": history,
    }
