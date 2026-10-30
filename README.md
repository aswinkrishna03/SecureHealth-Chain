# SecureHealth Chain
**A Lightweight Blockchain-Based Federated Learning Platform for Secure Health Records (EPP-BCFL)**

> **Authors**: Aswin Krishna N S, Aquil V K, Arjun M U, John Antony  
> **Domain**: Privacy-Preserving Health Informatics, Distributed Federated Learning & Live Blockchain Ledgers

---

## 1. Grounding in Recent Research (The EPP-BCFL Paper)

This project is directly designed and implemented around the breakthrough research publication:
> **"Blockchain-enabled federated learning with edge analytics for secure and efficient electronic health records management"**  
> *Munusamy S. & Jothi K. R.*  
> **Scientific Reports (Nature Portfolio)**, 2025 (15:27524). [DOI: 10.1038/s41598-025-12225-x]

### Translation of Research into SecureHealth Chain

| EPP-BCFL Research Concept | Research Paper Specification | SecureHealth Chain Implementation |
| :--- | :--- | :--- |
| **Edge Nodes Layer** | Local model training on private node datasets without sharing raw patient records. | Doctors train on-device neural models on local hospital EHR vitals. Raw clinical data never leaves the hospital edge silo. |
| **Differential Privacy (DP-SGD)** | Per-example gradient clipping ($C=1.0$), calibrated Gaussian noise ($\xi \sim \mathcal{N}(0, \sigma^2)$), and Rényi DP accounting. | Local training clips gradients and injects Gaussian noise based on privacy budget $\epsilon \in [0.2, 3.0]$ and $\delta = 10^{-5}$, mathematically preventing membership inference and reconstruction attacks. |
| **Blockchain Smart Contract Ledger** | Tamper-proof auditing and decentralized update verification. | Fully connected live Ethereum blockchain (Ganache RPC: `http://127.0.0.1:7545`) executing `SecureHealthRegistry.sol` via `web3.py`. Records real mined blocks and transactions for EHR integrity and model updates. |
| **Central Verification Gate** | Cryptographic verification of edge updates prior to aggregation. | Central Server checks the hospital's digital identity and verifies the incoming model update hash against on-chain smart contract commitments before admitting it into the global pool. |
| **Federated Averaging (FedAvg)** | Sample-count weighted parameter aggregation across verified nodes. | Aggregates verified model updates from multiple hospital nodes (e.g. Apollo, Aster, City General, Metro Health), publishes the Global Model on-chain, and broadcasts updated weights to all edge nodes. |
| **Clinical Integrity & Verification** | Tamper-evident verification of medical records without exposing patient data. | Canonical SHA-256 fingerprints sealed on-chain. Dynamic QR verification allows doctors and patients to instantly detect any unauthorized tampering. |

---

## 2. End-to-End System Architecture

```
                    +------------------------------------+
                    |     RESPONSIVE HEALTHCARE PORTAL   |
                    | [Admin]     [Doctor]     [Patient] |
                    +-----------------+------------------+
                                      | HTTP REST (JSON-RPC)
                    +-----------------v------------------+
                    |    Python Backend Application API  |
                    | (Port 5000: Auth, EHR, FL Engine)  |
                    +--------+------------------+--------+
                             |                  |
            +-----------------v----+      +------v-------------------+
            |  MySQL / MariaDB     |      | Live Ethereum Blockchain |
            |  Persistent Storage  |      | Ganache Testnet (RPC:7545|
            |  Users, EHR, Audits  |      | SecureHealthRegistry.sol |
            +----------------------+      +--------------------------+
                                                     ^
                                                     | Model Update Hashes
            +-----------------------------------------+--------------+
            |      MULTI-HOSPITAL FEDERATED LEARNING SUBSYSTEM       |
            |                                                        |
            | [Hospital Node 1]   [Hospital Node 2]   [Doctor Silo]  |
            |  PyTorch/SKL + DP    PyTorch/SKL + DP    DP-SGD Edge   |
            |         \                  |                 /         |
            |          +-----------------+----------------+          |
            |                            |                           |
            |       [Central Server FL Coordinator & Gate]           |
            |      (On-Chain Hash Verification + FedAvg Broadcast)   |
            +--------------------------------------------------------+
```

### The 4 Core Modules:

1. **Module 1: Role-Based Authentication & Persistent EHR Records**:
   - Distinct portals for **Admin**, **Doctor**, and **Patient**.
   - Backed by persistent **MySQL / MariaDB** with transparent in-memory fallback.
   - Doctor records patient vitals: resting blood pressure, cholesterol, max heart rate, blood glucose, oxygen saturation.

2. **Module 2: Doctor Edge Node & Privacy-Preserving DP-SGD Training**:
   - The doctor trains a neural disease prediction model directly inside the hospital edge silo.
   - **Zero-knowledge clinical privacy**: Raw patient data never leaves the hospital node.
   - Enforces Differential Privacy via gradient clipping ($C=1.0$) and calibrated Gaussian noise perturbation ($\epsilon=1.0, \sigma=0.2422$).
   - Generates a cryptographic SHA-256 model update fingerprint.

3. **Module 3: Ethereum Smart Contract & Central Verification Gate**:
   - Doctor pushes the model update hash to the Ethereum smart contract (`submitModelUpdate`).
   - The Central Server receives incoming updates from multiple hospitals (Apollo, Aster Medcity, City Central, Metro Health).
   - **Verification Gate**: Central Server cryptographically verifies each hospital's update hash against on-chain smart contract state before accepting it.
   - **Central Aggregation (FedAvg)**: Merges verified hospital weights into a new Global Disease Risk Prediction Model.
   - Publishes the Global Model hash on-chain (`publishGlobalModel`) and broadcasts updated weights to all edge nodes.

4. **Module 4: AI Risk Inference & Tamper-Evident QR Verification**:
   - Doctor and patient portals use the synchronized Global Model for heart disease and diabetes risk scoring.
   - Dynamic QR codes encode record UUID and cryptographic hash reference.
   - Instant tamper detection flags any altered records against on-chain smart contract records.

---

## 3. Technology Stack

- **Frontend**: Responsive Single-Page Application (HTML5, TailwindCSS, Heroicons, QR reader, Charting).
- **Backend**: Python 3.11, HTTP Server, Web3.py, Scikit-learn, NumPy, PyCryptodome, QRCode.
- **Relational Database**: MySQL 8.0 / MariaDB 10.4+ (Default database: `securehealth_db`, port 3306).
- **Blockchain Testnet**: Ganache CLI / GUI (RPC: `http://127.0.0.1:7545`, Network ID: `5777`, Chain ID: `1337`).
- **Smart Contract**: Solidity 0.8.20 compiled to Shanghai EVM (`SecureHealthRegistry.sol` deployed at `0x5f18C8CF1b857ec272B4357C0736b60E61324cd1`).

---

## 4. Quick Start & Execution Guide

### Prerequisites
1. **Python 3.10+** (installed with `pip`)
2. **Node.js & npm** (installed)
3. **Ganache** (`npm install -g ganache` or Ganache GUI)
4. **MySQL / MariaDB** (e.g. XAMPP, WAMP, or standalone MySQL service)

---

### Step 1: Start Live Ethereum Ganache Blockchain
Run the provided startup batch script from the project root:
```cmd
blockchain\start_ganache.bat
```
*This starts a local Ethereum blockchain on `127.0.0.1:7545` with the deterministic mnemonic and 10 pre-funded accounts (1000 ETH each).*

---

### Step 2: Install Python Dependencies
```cmd
pip install -r backend/requirements.txt
```

---

### Step 3: Run the SecureHealth Chain Server
```cmd
python backend/server.py
```
*The server will detect your live Ganache node and MySQL database, load the smart contract, and listen at:*  
👉 **`http://127.0.0.1:5000`**

Default logins:
- **Doctor Portal**: `doctor@securehealth.org` / `doctor`
- **Patient Portal**: `patient@securehealth.org` / `patient`
- **Admin Portal**: `admin@securehealth.org` / `admin`

---

### Step 4: Run the Complete E2E Integration Test Suite
To verify live on-chain transactions, smart contract execution, DP-SGD edge training, and FedAvg aggregation:
```cmd
python backend/test_blockchain_fl_e2e.py
```

---

## 5. Live Demonstration Workflow

1. **Doctor Collects Patient Vitals Privately**:
   - Sign in as **Doctor** (`doctor@securehealth.org` / `doctor`).
   - Navigate to **"Clinical Records & Sealing"** to register patient diagnosis and vitals.
   - The EHR SHA-256 fingerprint is immediately mined on the Ethereum blockchain (`registerEHR`).
2. **Doctor Trains Model on Private Edge Node**:
   - Navigate to **"Private Edge FL Training"** (`tab-doctor-edge-fl`).
   - Click **"⚡ Train Local Model & Apply Differential Privacy"**.
   - Notice the DP-SGD noise injected ($\epsilon=1.0, \sigma=0.2422$) and the generated SHA-256 model update hash.
   - Raw patient data remains strictly inside the hospital node.
3. **Doctor Pushes Update to Blockchain & Central Server**:
   - Click **"🚀 Push Model Update to Central Server & Blockchain"**.
   - The model update hash is anchored on Ethereum Ganache (`submitModelUpdate`) with a real transaction hash and block number.
4. **Central Server Verifies Hospital Hashes & Runs FedAvg**:
   - Sign in as **Admin** (`admin@securehealth.org` / `admin`).
   - Open **"Federated Learning Coordinator"** (`tab-fl`).
   - View the **"Incoming Hospital Model Updates & Central Verification Gate"**:
     - See updates from Apollo, Aster, City Central, and Metro Health.
     - Each update displays: `🟢 VERIFIED AUTHENTIC & ACCEPTED`.
   - Click **"🚀 Run FedAvg & Broadcast Global Model"**.
   - FedAvg aggregates the verified hospital updates into a new Global Model.
   - The Global Model is published on Ethereum (`publishGlobalModel`) and broadcast back to all hospitals.
5. **On-Chain Block Explorer**:
   - Open **"Blockchain Explorer"** (`tab-blockchain`).
   - Inspect the real mined Ethereum blocks, transaction hashes, gas consumption, and smart contract executions.
