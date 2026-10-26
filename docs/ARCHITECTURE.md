# SecureHealth Chain: Project Architecture & Technical Roadmap

## Project Overview
- **Title**: SecureHealth Chain: A Lightweight Blockchain-Based Federated Learning Platform for Secure Health Records
- **Authors**: Aswin Krishna N S, Aquil V K, Arjun M U, John Antony
- **Reference Publication**: *Blockchain-enabled federated learning with edge analytics for secure and efficient electronic health records management* (Munusamy S & Jothi K R, *Scientific Reports*, Nature Portfolio, 2025)

---

## 1. System Overview & Problem Statement
Centralized Electronic Health Record (EHR) platforms suffer from single-point-of-failure vulnerabilities, insider tampering, and regulatory barriers against multi-institutional data sharing. While theoretical blockchain-FL frameworks (such as EPP-BCFL) demonstrate cryptographic resilience, their full implementations (utilizing zk-SNARKs and homomorphic secret sharing across hundreds of nodes) are computationally heavy and unsuitable for resource-constrained, real-time college prototypes.

**SecureHealth Chain** implements a lightweight, modular, and demonstrably secure solution:
- **Federated Learning via Flower (`flwr`)**: Trains disease prediction models across hospital silos without sharing patient data.
- **Differential Privacy ($\epsilon$-budget)**: Masks individual records via Gaussian noise perturbation before gradient exchange.
- **Blockchain Verification via Ethereum Ganache**: Immutably records EHR cryptographic hashes and model update proofs in Solidity smart contracts.
- **Role-Based Portals (Admin, Doctor, Patient)**: Clean, intuitive interfaces built with React.js and Flask.
- **QR Code Verification Engine**: Embeds blockchain transaction proofs into record QR codes for instant offline/online integrity validation.

---

## 2. Directory Structure

```
MAINNN PROJECT/
├── docs/                           # Project design, documentation, and diagrams
├── backend/                        # Flask API server, auth, routes, and DB
│   ├── app.py                      # Flask entry point
│   ├── config.py                   # Configuration and secret keys
│   ├── database.py                 # SQLAlchemy / MySQL connection
│   ├── models/                     # User, EHR, and Audit log models
│   ├── routes/                     # Auth, EHR, AI, Verification, and FL routes
│   ├── services/                   # Web3 Ganache bridge, QR generator, AI inference
│   └── requirements.txt            # Python backend dependencies
├── blockchain/                     # Smart contracts and deployment
│   ├── contracts/
│   │   └── SecureHealthRegistry.sol# Solidity contract for EHR & FL hashes
│   ├── scripts/
│   │   └── deploy.py               # Web3 deployment script to Ganache
│   └── build/                      # Compiled ABIs
├── fl_core/                        # Federated Learning Subsystem
│   ├── client.py                   # Hospital node client (with DP noise)
│   ├── server.py                   # FL Central Aggregator (FedAvg)
│   ├── model.py                    # Disease risk prediction model
│   └── dataset/                    # Siloed hospital EHR datasets
└── frontend/                       # React.js web client
    ├── src/
    │   ├── components/             # Reusable UI widgets & QR scanner
    │   ├── pages/                  # Role portals: Admin, Doctor, Patient
    │   └── services/               # Axios API client
    └── package.json
```

---

## 3. Four Core Modules (As per Approved Proposal)

### Module 1: User Authentication & Role Management
- Multi-role authentication (Admin, Doctor, Patient) using JWT (JSON Web Tokens) and bcrypt password hashing.
- Role-based route authorization guards.
- Patient EHR profile management and doctor clinical review interfaces.

### Module 2: Local AI Model & Federated Learning Client
- Clinical Disease Risk Prediction (Cardiovascular Heart Disease tabular dataset).
- Local model training using PyTorch / Scikit-learn at hospital node level.
- Differential Privacy (DP) layer injecting Gaussian noise $\xi \sim \mathcal{N}(0, \sigma^2)$ to model parameters.
- Client-side computation of update hash $H_i = \text{SHA256}(\theta^{t+1}_i)$.

### Module 3: Federated Aggregation & Blockchain Hash Storage
- Central coordinator running Flower FL server (`flwr.server`).
- Federated Averaging (FedAvg) aggregation over verified participating hospital nodes.
- Solidity smart contract (`SecureHealthRegistry.sol`) running on Ethereum Ganache.
- Stores immutable cryptographic hashes of EHR records and global model updates.

### Module 4: AI Health Risk Dashboard & QR Verification
- Real-time clinical risk prediction interface (computes probability of disease based on user vitals).
- Automatic generation of cryptographic QR codes linking record data to Ganache transaction hashes.
- Camera-based / file-upload QR scanner for doctors and auditors to instantly verify if an EHR record has been tampered with or modified.
