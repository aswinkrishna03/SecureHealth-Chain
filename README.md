# SecureHealth Chain
**A Lightweight Blockchain-Based Federated Learning Platform for Secure Health Records**

> **Authors**: Aswin Krishna N S, Aquil V K, Arjun M U, John Antony  
> **Domain**: Privacy-Preserving Health Informatics, Distributed Federated Learning & Blockchain Ledgers

---

## 1. Grounding in Recent Research (The EPP-BCFL Paper)

This project is directly designed and modeled around the breakthrough research publication:
> **"Blockchain-enabled federated learning with edge analytics for secure and efficient electronic health records management"**  
> *Munusamy S. & Jothi K. R.*  
> **Scientific Reports (Nature Portfolio)**, 2025 (15:27524). [DOI: 10.1038/s41598-025-12225-x]

### Translation of Research into SecureHealth Chain

| EPP-BCFL Research Concept | Research Paper Specification | SecureHealth Chain Implementation |
| :--- | :--- | :--- |
| **Edge Nodes Layer** | Local model training on private node datasets without sharing raw patient records. | Flower client/server code is present; the dashboard currently runs a local simulation with synthetic silo partitions. |
| **Differential Privacy (DP)** | Per-example clipping, calibrated Gaussian noise, and composition accounting. | Training uses clipped per-patient gradients and an RDP epsilon/delta bound for one requested training invocation. Exact evaluation metrics and repeated invocations are outside that bound. |
| **Homomorphic Encryption (HE)** | Encrypt client model updates and aggregate without decrypting individual updates. | TenSEAL CKKS encrypts each node model; the coordinator performs sample-weighted vector aggregation on ciphertexts and decrypts only the aggregate. This local demo keeps the key custodian in the same process. |
| **Adaptive Model Aggregation (AMA)** | Paper discusses adaptive aggregation, while its explicit global-model equation is sample-count weighted FedAvg. | The dashboard implements the explicit FedAvg equation. The paper does not give a complete AMA weighting formula, so the simulation does not invent one. |
| **Blockchain Consensus & Ledger** | PoS + BFT consensus for tamper-proof auditing and decentralized update verification. | The dashboard uses an in-memory Python ledger. The Solidity contract is present but not wired to these API routes. |
| **Clinical Integrity & Verification** | Tamper-evident verification without exposing patient data. | QR codes carry a record identifier and hash reference; verification compares current record content with the local demo ledger. |

---

## 2. System Architecture & 4 Core Modules

```
                    +------------------------------------+
                    |        REACT.JS FRONTEND           |
                    | [Admin]     [Doctor]     [Patient] |
                    +-----------------+------------------+
                                      | HTTP REST / opaque demo token
                    +-----------------v------------------+
                    |   Python standard-library API       |
                    |   (Port 5000: Auth, EHR, QR)        |
                    +--------+------------------+--------+
                             |                  |
           +-----------------v----+      +------v-------------------+
           |  In-memory demo data |      | In-memory Python ledger  |
           | Users, EHR, audit    |      | Solidity not connected   |
           +---------------------+      +--------------------------+
                                                     ^
                                                     | Model Update Hashes
           +-----------------------------------------+--------------+
           |           FLOWER FEDERATED LEARNING SUBSYSTEM          |
           |                                                        |
           |  [Hospital Node 1]   [Hospital Node 2]   [Node 3]      |
           |   PyTorch/SKL + DP    PyTorch/SKL + DP    PyTorch + DP |
           |          \                  |                 /        |
           |           +-----------------+----------------+         |
           |                             |                          |
           |             [Flower FL Central Aggregator]             |
           |               (FedAvg + Model Hash Logger)             |
           +--------------------------------------------------------+
```

### Module 1: User Authentication & Role Management
- Demo login for **Admin**, **Doctor**, and **Patient** roles; public registration creates patient accounts only.
- Role-based dashboard visibility and API authorization use expiring in-memory bearer sessions. Restarting the server resets users and sessions.
- Patient EHR profile upload and management.
- Doctor interface for reviewing patient clinical records and AI predictions.

### Module 2: Local AI Model & Federated Learning Client
- Local training of disease prediction models (e.g. Cardiovascular Heart Disease) on hospital/node-level EHR data.
- Each client clips per-patient logistic-loss gradients to L2 norm `C=1`, adds calibrated Gaussian noise, and accounts for all local steps and requested rounds with an RDP bound (`delta=1e-5`). The reported guarantee applies to training updates in one request; exact evaluation metrics and repeated requests are not covered.
- The coordinator applies the paper's explicit FedAvg equation over TenSEAL CKKS ciphertext vectors, weighted by each node's public local training count. The ephemeral secret key remains in the same process for this demo; production requires a separate key custodian or threshold decryption.
- Install `backend/requirements.txt` to add the pinned TenSEAL dependency used for CKKS encryption.
- Federated Learning client setup using **Flower (`flwr`)**.
- Model update generation without sharing raw patient data.
- Evaluation and accuracy reporting prior to parameter exchange.

### Module 3: Federated Aggregation & Hash Audit
- Central FL server aggregating model updates using **Federated Averaging (FedAvg)**.
- Cryptographic SHA-256 hashing of model updates ($H_i$) and medical records ($H_{\text{EHR}}$).
- The current dashboard stores hashes in a local in-memory demo ledger. Solidity/Ganache integration remains future work.
- Global model update generation and redistribution to nodes.
- Validation of stored hashes against incoming updates before acceptance.

### Module 4: Risk Score Dashboard & QR Verification
- Local federated-training demo automatically reads `~/Downloads/synthea_sample_data_csv_latest.zip` when present (override with `SYNTHEA_DATA_ZIP`); otherwise it uses the bundled heart-disease sample.
- The Synthea path uses demographics and selected latest vitals/labs to classify recorded diabetes/prediabetes status across three deterministic virtual edge partitions. This small synthetic sample is educational, not a clinical model or evidence of real multi-hospital federation.
- QR code generation embeds a record identifier and hash reference for verification against the local demo ledger.
- QR-based scan-and-verify workflow for authorized record integrity checks.
- Audit logging of verification events, timestamps, and tamper alerts.

---

## 3. Technology Stack

- **Frontend**: React.js, TailwindCSS / Bootstrap, Axios, `html5-qrcode` / `react-qr-reader`
- **Backend**: Python 3.11, Flask, Flask-CORS, PyCryptodome, QRCode, Pillow
- **Database**: MySQL schema is included but the demo API currently uses in-memory data
- **Blockchain**: Solidity contract and optional Ganache service; not integrated into the demo API
- **AI & Federated Learning**: Flower (`flwr`), PyTorch, Scikit-learn, NumPy, Pandas

---

## 4. Quick Start & Execution Guide

### Prerequisites
1. **Python 3.9+** (installed)
2. **Node.js v18+ & npm** (installed)
3. **Ganache** (Ganache GUI or `npm install -g ganache`)
4. **MySQL Server** (optional for local mock; required for production DB)

---

### Step 1: Install Backend Dependencies
```powershell
cd backend
pip install -r requirements.txt
```
The React app uses `server.py`, which provides the Python standard-library API. `app.py` is an earlier experimental Flask API and is not compatible with the current sign-in flow. MySQL and Ganache components are not yet wired into every dashboard route.

### Step 2: Optional Integrations
The dashboard demo does not use MySQL or Ganache yet. `backend/schema.sql` and the Solidity contract are project artifacts for future integration; starting these services does not connect them to `server.py`.

### Step 3: Run the Demo API
```powershell
cd backend
python server.py
```
The API will start on `http://127.0.0.1:5000`. The React development server proxies API and QR requests to it.

Demo accounts:
- Doctor: `doctor@securehealth.org` / `doctor`
- Patient: `patient@securehealth.org` / `patient`
- Admin: `admin@securehealth.org` / `admin`

The demo server keeps users, records, sessions, audit events, and its ledger in memory. Restarting it resets the demo state. Its current ledger is a local Python simulation; the Solidity contract and Ganache transaction path require separate deployment and integration before the system can claim on-chain storage.

---

### Step 4: Run the React Frontend
In another terminal:
```powershell
cd frontend
npm install
npm run dev
```
Open the Vite URL shown in the terminal (normally `http://localhost:3000`).

### Optional: Run the Separate Flower Client/Server
These processes are independent of the dashboard's local training simulation. In separate terminals from the repository root:
1. **Terminal 1 (FL Server Aggregator)**:
   ```powershell
   python fl_core/server.py
   ```
2. **Terminal 2 (Hospital Client 1)**:
   ```powershell
   python fl_core/client.py Hospital-Apollo
   ```
3. **Terminal 3 (Hospital Client 2)**:
   ```powershell
   python fl_core/client.py Hospital-Aster
   ```
*Observe how weights are trained locally on private patient data, perturbed with Differential Privacy Gaussian noise, hashed, and aggregated without sharing raw clinical records.*

---

## 5. Demo Workflow

1. **Role Login**:
   - Sign in as **Doctor** (`doctor@securehealth.org` / `doctor`).
2. **AI Health Risk Prediction**:
   - Open the Risk Predictor form.
   - Enter patient clinical vitals: Age (58), BP (145), Cholesterol (260), Max HR (115), Angina (Yes).
   - Review the sample-data logistic-model score and holdout accuracy; neither is clinically validated or for diagnosis.
3. **Sealing EHR hash and QR**:
   - Fill in Diagnosis: *"Coronary Artery Disease Stage II"*.
   - Click **"Seal Record Hash & Generate QR"**.
   - The demo API computes a canonical SHA-256 hash and stores it in its local in-memory ledger.
4. **QR Code Verification**:
   - Sign in as **Patient** (`patient@securehealth.org` / `patient`) or Doctor, then scan the QR code or enter its record ID.
   - Verification compares the current record hash against the demo ledger entry.
5. **Tamper-Detection Proof (Viva Highlight)**:
   - Sign in as **Admin** (`admin@securehealth.org` / `admin`) and use the tamper demo control.
   - Verify the record again to see the hash mismatch flagged.

---

## 6. Publications & Deliverables Aligned
- **Journal/Conference Paper**: Manuscript draft based on EPP-BCFL lightweight adaptation and tabular clinical benchmarking.
- **Web Application**: Role-gated educational prototype. Persistent storage, live smart-contract integration, formal privacy accounting, and a clinically validated risk model remain future work.

