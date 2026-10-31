-- SecureHealth Chain MySQL Database Schema
-- Multi-Hospital & Multi-Doctor Clinical Verification Architecture

CREATE DATABASE IF NOT EXISTS securehealth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE securehealth_db;

-- 1. Registered Hospitals Table
CREATE TABLE IF NOT EXISTS hospitals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id VARCHAR(64) NOT NULL UNIQUE,
    hospital_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    node_id VARCHAR(64) NOT NULL,
    hospital_hash VARCHAR(66) NOT NULL, -- On-chain SHA-256 identity hash
    eth_address VARCHAR(42) DEFAULT NULL,
    is_registered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hosp_id (hospital_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Users Table (Doctors, Head Doctors, Patients, Admins)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'doctor', 'patient') NOT NULL,
    hospital_id VARCHAR(64) DEFAULT 'HOSP-METRO-01',
    hospital_name VARCHAR(150) DEFAULT 'Metro Health General Hospital',
    specialty VARCHAR(100) DEFAULT 'General Medicine',
    license_number VARCHAR(50) DEFAULT NULL,
    is_head_doctor BOOLEAN DEFAULT FALSE,
    doctor_hash VARCHAR(66) DEFAULT NULL, -- On-chain cryptographic doctor identity hash
    is_verified BOOLEAN DEFAULT TRUE,
    eth_address VARCHAR(42) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_hospital (hospital_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Electronic Health Records (EHR) Table
CREATE TABLE IF NOT EXISTS ehr_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_uuid VARCHAR(64) NOT NULL UNIQUE,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    patient_name VARCHAR(100) DEFAULT NULL,
    doctor_name VARCHAR(100) DEFAULT NULL,
    doctor_specialty VARCHAR(100) DEFAULT 'General Medicine',
    doctor_license VARCHAR(50) DEFAULT NULL,
    hospital_id VARCHAR(64) DEFAULT 'HOSP-METRO-01',
    hospital_name VARCHAR(150) NOT NULL,
    diagnosis VARCHAR(255) NOT NULL,
    clinical_metrics JSON NOT NULL, -- Tabular vitals (age, bp, cholesterol, etc.)
    record_hash VARCHAR(66) NOT NULL, -- SHA-256 hash matching blockchain
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL, -- Ganache transaction receipt
    qr_code_url VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_patient (patient_id),
    INDEX idx_hash (record_hash),
    INDEX idx_hosp (hospital_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Edge Silo Local Model Updates & Head Doctor Approvals Table
CREATE TABLE IF NOT EXISTS edge_model_updates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    update_uuid VARCHAR(64) NOT NULL UNIQUE,
    round_number INT NOT NULL,
    hospital_id VARCHAR(64) NOT NULL,
    hospital_name VARCHAR(150) NOT NULL,
    doctor_id INT NOT NULL,
    doctor_name VARCHAR(100) NOT NULL,
    doctor_specialty VARCHAR(100) NOT NULL,
    model_hash VARCHAR(66) NOT NULL,
    samples_count INT NOT NULL,
    local_loss FLOAT NOT NULL,
    local_accuracy FLOAT NOT NULL,
    dp_epsilon FLOAT NOT NULL,
    noise_sigma FLOAT NOT NULL,
    head_doctor_id INT DEFAULT NULL,
    head_doctor_name VARCHAR(100) DEFAULT NULL,
    head_doctor_signature_hash VARCHAR(66) DEFAULT NULL,
    approval_status ENUM('PENDING_REVIEW', 'APPROVED_BY_HEAD_DOCTOR', 'REJECTED') DEFAULT 'PENDING_REVIEW',
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL,
    central_verification_status ENUM('PENDING', 'VERIFIED_ACCEPTED', 'REJECTED_UNVERIFIED') DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_round (round_number),
    INDEX idx_hosp_update (hospital_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Federated Learning Training Rounds Audit Table
CREATE TABLE IF NOT EXISTS fl_rounds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    round_number INT NOT NULL,
    global_model_hash VARCHAR(66) NOT NULL,
    accuracy FLOAT NOT NULL,
    precision_score FLOAT DEFAULT NULL,
    recall_score FLOAT DEFAULT NULL,
    f1_score FLOAT DEFAULT NULL,
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL,
    participating_nodes INT DEFAULT 4,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Audit & Verification Trail Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_uuid VARCHAR(64) NOT NULL,
    action VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'VERIFIED_AUTHENTIC',
    performed_by INT DEFAULT NULL,
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_record (record_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
