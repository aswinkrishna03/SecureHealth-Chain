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
| **Edge Nodes Layer** | Local model training on private node datasets without sharing raw patient records. | **Hospital Node Clients (`fl_core/client.py`)**: Individual clinics/hospitals train local classifiers on private tabular EHR datasets. |
| **Differential Privacy (DP)** | $\theta^{t+1}_i = \theta^t_i - \eta \nabla L_i(\theta^t_i, D_i) + \xi$ where $\xi \sim \mathcal{N}(0, \sigma^2)$ | Gaussian noise layer injected into model updates with configurable privacy budget ($\epsilon$), defending against inference attacks while preserving accuracy (>92%). |
| **Adaptive Model Aggregation (AMA)** | Aggregates updates based on data quality, node reliability, and sample size weighting. | **Flower Aggregator (`fl_core/server.py`)**: Sample-weighted FedAvg coordinating multi-hospital learning rounds. |
| **Blockchain Consensus & Ledger** | PoS + BFT consensus for tamper-proof auditing and decentralized update verification. | **Ethereum Ganache & Solidity (`SecureHealthRegistry.sol`)**: Records cryptographic SHA-256 hashes of EHRs and training updates on a local private blockchain. |
| **Clinical Integrity & Verification** | Tamper-evident verification without exposing patient data. | **QR-Code Scan & Blockchain Verification**: Every EHR generates a signed QR code linking to on-chain transaction hashes. Tampering is flagged instantly. |

---

## 2. System Architecture & 4 Core Modules

```
                    +------------------------------------+
                    |        REACT.JS FRONTEND           |
                    | [Admin]     [Doctor]     [Patient] |
                    +-----------------+------------------+
                                      | HTTP REST / JWT
                    +-----------------v------------------+
                    |       FLASK REST BACKEND API       |
                    |   (Port 5000: Routes, Auth, QR)    |
                    +--------+------------------+--------+
                             |                  |
           +-----------------v----+      +------v-------------------+
           |    MYSQL DATABASE    |      |  ETHEREUM GANACHE LEDGER |
           | Users, EHR Metadata, |      |  SecureHealthRegistry.sol|
           | Verification Logs    |      |  Immutable Record Hashes |
           +----------------------+      +--------------------------+
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
- Secure registration and login for **Admin**, **Doctor**, and **Patient** roles.
- Role-based dashboard access, route guards, and permissions.
- Patient EHR profile upload and management.
- Doctor interface for reviewing patient clinical records and AI predictions.

### Module 2: Local AI Model & Federated Learning Client
- Local training of disease prediction models (e.g. Cardiovascular Heart Disease) on hospital/node-level EHR data.
- Federated Learning client setup using **Flower (`flwr`)**.
- Model update generation without sharing raw patient data.
- Differential Privacy perturbation ($\xi \sim \mathcal{N}(0, \sigma^2)$) applied to model weights before submission.
- Evaluation and accuracy reporting prior to parameter exchange.

### Module 3: Federated Aggregation & Blockchain Hash Storage
- Central FL server aggregating model updates using **Federated Averaging (FedAvg)**.
- Cryptographic SHA-256 hashing of model updates ($H_i$) and medical records ($H_{\text{EHR}}$).
- Tamper-evident storage on a **Ganache-based Ethereum blockchain** via Solidity smart contracts.
- Global model update generation and redistribution to nodes.
- Validation of stored hashes against incoming updates before acceptance.

### Module 4: AI Health Risk Dashboard & QR Verification
- AI Health Risk Prediction Dashboard showing disease risk probability, clinical indicators, and blockchain status.
- QR code generation embedding the blockchain transaction hash for each medical record.
- QR-based scan-and-verify workflow for authorized record integrity checks.
- Audit logging of verification events, timestamps, and tamper alerts.

---

## 3. Technology Stack

- **Frontend**: React.js, TailwindCSS / Bootstrap, Axios, `html5-qrcode` / `react-qr-reader`
- **Backend**: Python 3.11, Flask, Flask-CORS, PyCryptodome, QRCode, Pillow
- **Database**: MySQL Server (with `mysql-connector-python` & `SQLAlchemy`)
- **Blockchain**: Ethereum Ganache, Solidity (`v0.8.19`), Web3.py / Truffle
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

### Step 2: Set Up Database (MySQL)
Run the SQL schema in your MySQL environment:
```powershell
mysql -u root -p < backend/schema.sql
```

### Step 3: Start Ganache Ethereum Blockchain
Launch Ganache GUI (listening on `HTTP://127.0.0.1:7545`) or run the CLI:
```powershell
npx ganache --port 7545
```

### Step 4: Run the Flask Backend
```powershell
cd backend
python app.py
```
*The backend API will start on `http://127.0.0.1:5000`.*

---

### Step 5: Test Federated Learning Simulation (Flower)
In two separate terminal windows:
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

## 5. Live Demonstration Workflow for Project Viva

1. **Role Login**:
   - Log in as **Doctor** (`doctor@securehealth.org` / `doctor123`).
2. **AI Health Risk Prediction**:
   - Open the Risk Predictor form.
   - Enter patient clinical vitals: Age (58), BP (145), Cholesterol (260), Max HR (115), Angina (Yes).
   - Click **"Predict Disease Risk"** $\rightarrow$ View risk probability (e.g., **85.0% - High Risk**).
3. **Sealing EHR with Blockchain & QR**:
   - Fill in Diagnosis: *"Coronary Artery Disease Stage II"*.
   - Click **"Sign & Seal Record to Blockchain"**.
   - The backend computes the canonical SHA-256 hash, registers it onto Ethereum Ganache, and generates a tamper-evident QR code embedding the transaction hash.
4. **QR Code Verification**:
   - Log in as **Patient** (`patient@securehealth.org`) or open the **Verify Record** scanner.
   - Scan or view the QR code: Status shows **"VERIFIED AUTHENTIC & IMMUTABLE"** with Ganache Block Number and Timestamp.
5. **Tamper-Detection Proof (Viva Highlight)**:
   - Trigger the demonstration tampering endpoint (`/api/demo/tamper-record`).
   - Re-scan the QR code.
   - The system immediately flags **"WARNING: RECORD TAMPERED"** because the recomputed hash does not match the on-chain Ganache hash!

---

## 6. Publications & Deliverables Aligned
- **Journal/Conference Paper**: Manuscript draft based on EPP-BCFL lightweight adaptation and tabular clinical benchmarking.
- **Web Application**: Fully functional role-based healthcare portal with Ganache smart contracts and Flower federated aggregation.
