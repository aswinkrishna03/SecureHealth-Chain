-- SecureHealth Chain MySQL Database Schema
-- Run this script in MySQL Workbench or via MySQL CLI:
-- mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS securehealth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE securehealth_db;

-- 1. Users Table (Role-based access: Admin, Doctor, Patient)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'doctor', 'patient') NOT NULL,
    hospital_name VARCHAR(150) DEFAULT 'Metro Health General Hospital',
    eth_address VARCHAR(42) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Electronic Health Records (EHR) Table
CREATE TABLE IF NOT EXISTS ehr_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_uuid VARCHAR(64) NOT NULL UNIQUE,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    patient_name VARCHAR(100) DEFAULT NULL,
    doctor_name VARCHAR(100) DEFAULT NULL,
    hospital_name VARCHAR(150) NOT NULL,
    diagnosis VARCHAR(255) NOT NULL,
    clinical_metrics JSON NOT NULL, -- Tabular clinical vitals (age, bp, cholesterol, etc.)
    record_hash VARCHAR(66) NOT NULL, -- SHA-256 hash matching blockchain
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL, -- Ganache transaction receipt
    qr_code_url VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_patient (patient_id),
    INDEX idx_hash (record_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Federated Learning Training Rounds Audit Table
CREATE TABLE IF NOT EXISTS fl_rounds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    round_number INT NOT NULL,
    global_model_hash VARCHAR(66) NOT NULL,
    accuracy FLOAT NOT NULL,
    precision_score FLOAT DEFAULT NULL,
    recall_score FLOAT DEFAULT NULL,
    f1_score FLOAT DEFAULT NULL,
    blockchain_tx_hash VARCHAR(66) DEFAULT NULL,
    participating_nodes INT DEFAULT 3,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Audit & Verification Trail Table
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

-- Default Demo Seed Data (PBKDF2 SHA-256)
INSERT IGNORE INTO users (id, name, email, password_hash, role, hospital_name) VALUES
(1, 'System Administrator', 'admin@securehealth.org', 'pbkdf2:sha256:600000$demo$hashedpassword', 'admin', 'Health Network HQ'),
(2, 'Dr. Sarah Jenkins', 'doctor@securehealth.org', 'pbkdf2:sha256:600000$demo$hashedpassword', 'doctor', 'Metro Health General Hospital'),
(3, 'Aswin Krishna', 'patient@securehealth.org', 'pbkdf2:sha256:600000$demo$hashedpassword', 'patient', 'Metro Health General Hospital');
