"""
SecureHealth Chain - MySQL Database Service
Dual-Mode Database Architecture:
- Primary: Real-time MySQL persistence (hospitals, users, ehr_records, edge_model_updates, fl_rounds, audit_logs)
- Resilient Fallback: In-memory store when MySQL is offline / unreachable
Supports Multi-Hospital and Multi-Doctor hierarchical verification architecture.
"""

import os
import json
import datetime
import hashlib
import hmac
import secrets
from typing import Dict, Any, List, Optional

# Load .env file if present
def load_env_file():
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        os.path.abspath(".env")
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass

load_env_file()

# Password hashing utilities
def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return f"{salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    if not stored or not password:
        return False
    try:
        if "$" in stored:
            parts = stored.split("$")
            if len(parts) == 2:
                salt_hex, digest_hex = parts
                candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
                return hmac.compare_digest(candidate, digest_hex)
            elif len(parts) == 4 and parts[0] == "pbkdf2:sha256":
                salt_str = parts[2]
                digest_hex = parts[3]
                calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_str.encode("utf-8"), int(parts[1]))
                return hmac.compare_digest(calc.hex(), digest_hex)
        return False
    except Exception:
        return False

# Database Driver selection (PyMySQL or mysql-connector-python)
DB_DRIVER = None
try:
    import pymysql
    import pymysql.cursors
    DB_DRIVER = "pymysql"
except ImportError:
    try:
        import mysql.connector
        DB_DRIVER = "mysql.connector"
    except ImportError:
        DB_DRIVER = None

def compute_hospital_hash(hospital_id: str, hospital_name: str, node_id: str) -> str:
    raw = f"HOSPITAL:{hospital_id}:{hospital_name}:{node_id}"
    return "0x" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def compute_doctor_hash(doctor_id: str, hospital_id: str, license_number: str, specialty: str) -> str:
    raw = f"DOCTOR:{doctor_id}:{hospital_id}:{license_number}:{specialty}"
    return "0x" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

class DatabaseService:
    def __init__(self):
        self.host = os.environ.get("MYSQL_HOST", "127.0.0.1")
        self.port = int(os.environ.get("MYSQL_PORT", 3306))
        self.user = os.environ.get("MYSQL_USER", "root")
        self.password = os.environ.get("MYSQL_PASSWORD", "")
        self.database = os.environ.get("MYSQL_DATABASE", "securehealth_db")
        
        self.driver = DB_DRIVER
        self.is_connected = False
        self.last_error = None
        
        # In-memory storage for resilient fallback and fast cache
        self.hospitals_cache: Dict[str, Dict[str, Any]] = {}
        self.users_cache: Dict[str, Dict[str, Any]] = {}
        self.users_by_id: Dict[int, Dict[str, Any]] = {}
        self.ehr_cache: Dict[str, Dict[str, Any]] = {}
        self.edge_updates_cache: Dict[str, Dict[str, Any]] = {}
        self.audit_cache: List[Dict[str, Any]] = []
        self.fl_cache: List[Dict[str, Any]] = []
        
        # Populate initial default records for fallback
        self._seed_in_memory_defaults()
        
        # Attempt MySQL connection
        self.init_database()

    def _seed_in_memory_defaults(self):
        """Seed multi-hospital and multi-doctor network defaults."""
        default_hospitals = [
            {
                "id": 1,
                "hospital_id": "HOSP-METRO-01",
                "hospital_name": "Metro Health General Hospital",
                "city": "New York",
                "node_id": "Hospital-Edge-metro-health",
                "hospital_hash": compute_hospital_hash("HOSP-METRO-01", "Metro Health General Hospital", "Hospital-Edge-metro-health"),
                "eth_address": "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51",
                "is_registered": True
            },
            {
                "id": 2,
                "hospital_id": "HOSP-APOLLO-02",
                "hospital_name": "Apollo Healthcare Network",
                "city": "Chicago",
                "node_id": "Hospital-Edge-apollo-health",
                "hospital_hash": compute_hospital_hash("HOSP-APOLLO-02", "Apollo Healthcare Network", "Hospital-Edge-apollo-health"),
                "eth_address": "0x299480aE0259E42A94BCaec8530f01Ce4173428D",
                "is_registered": True
            },
            {
                "id": 3,
                "hospital_id": "HOSP-ASTER-03",
                "hospital_name": "Aster Medcity Silo",
                "city": "San Francisco",
                "node_id": "Hospital-Edge-aster-medcity",
                "hospital_hash": compute_hospital_hash("HOSP-ASTER-03", "Aster Medcity Silo", "Hospital-Edge-aster-medcity"),
                "eth_address": "0x45Bc9f17C10Fcd882E3790f7390986f70D825eBc",
                "is_registered": True
            },
            {
                "id": 4,
                "hospital_id": "HOSP-CITY-04",
                "hospital_name": "City Central Clinic",
                "city": "Boston",
                "node_id": "Hospital-Edge-city-central",
                "hospital_hash": compute_hospital_hash("HOSP-CITY-04", "City Central Clinic", "Hospital-Edge-city-central"),
                "eth_address": "0x2c06353B41FB7076511A7f47F82BEE53D1A31AAe",
                "is_registered": True
            }
        ]
        for h in default_hospitals:
            self.hospitals_cache[h["hospital_id"]] = h

        # Multi-Doctor network with specializations & Head Doctors
        default_users = [
            {
                "id": 1,
                "name": "System Administrator",
                "email": "admin@securehealth.org",
                "password_hash": hash_password("admin"),
                "role": "admin",
                "hospital_id": "CENTRAL-HQ",
                "hospital_name": "Health Network Central Coordinator",
                "specialty": "Central FL Architecture",
                "license_number": "ADMIN-COORD-0001",
                "is_head_doctor": False,
                "doctor_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
                "is_verified": True,
                "eth_address": None,
                "created_at": "2026-10-26T20:00:00Z"
            },
            # Hospital 1: Metro Health General Hospital
            {
                "id": 2,
                "name": "Dr. Sarah Jenkins",
                "email": "doctor@securehealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_id": "HOSP-METRO-01",
                "hospital_name": "Metro Health General Hospital",
                "specialty": "Cardiologist",
                "license_number": "MD-CARDIO-8821",
                "is_head_doctor": False,
                "doctor_hash": compute_doctor_hash("DOC-METRO-01", "HOSP-METRO-01", "MD-CARDIO-8821", "Cardiologist"),
                "is_verified": True,
                "eth_address": "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51",
                "created_at": "2026-10-26T20:05:00Z"
            },
            {
                "id": 3,
                "name": "Dr. Alex Morgan",
                "email": "alex.morgan@metrohealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_id": "HOSP-METRO-01",
                "hospital_name": "Metro Health General Hospital",
                "specialty": "General Physician",
                "license_number": "MD-INT-4412",
                "is_head_doctor": False,
                "doctor_hash": compute_doctor_hash("DOC-METRO-02", "HOSP-METRO-01", "MD-INT-4412", "General Physician"),
                "is_verified": True,
                "eth_address": "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51",
                "created_at": "2026-10-26T20:06:00Z"
            },
            {
                "id": 4,
                "name": "Dr. Marcus Vance (CMO)",
                "email": "head.doctor@metrohealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_id": "HOSP-METRO-01",
                "hospital_name": "Metro Health General Hospital",
                "specialty": "Chief Medical Officer",
                "license_number": "MD-CHIEF-0010",
                "is_head_doctor": True,
                "doctor_hash": compute_doctor_hash("DOC-METRO-HEAD", "HOSP-METRO-01", "MD-CHIEF-0010", "Chief Medical Officer"),
                "is_verified": True,
                "eth_address": "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51",
                "created_at": "2026-10-26T20:07:00Z"
            },
            # Hospital 2: Apollo Healthcare Network
            {
                "id": 5,
                "name": "Dr. Priya Nair",
                "email": "priya.nair@apollohealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_id": "HOSP-APOLLO-02",
                "hospital_name": "Apollo Healthcare Network",
                "specialty": "Cardiologist",
                "license_number": "MD-CARDIO-5510",
                "is_head_doctor": False,
                "doctor_hash": compute_doctor_hash("DOC-APOLLO-01", "HOSP-APOLLO-02", "MD-CARDIO-5510", "Cardiologist"),
                "is_verified": True,
                "eth_address": "0x299480aE0259E42A94BCaec8530f01Ce4173428D",
                "created_at": "2026-10-26T20:08:00Z"
            },
            {
                "id": 6,
                "name": "Dr. Elena Rostova (CMO)",
                "email": "head.doctor@apollohealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_id": "HOSP-APOLLO-02",
                "hospital_name": "Apollo Healthcare Network",
                "specialty": "Chief Medical Officer",
                "license_number": "MD-CHIEF-0020",
                "is_head_doctor": True,
                "doctor_hash": compute_doctor_hash("DOC-APOLLO-HEAD", "HOSP-APOLLO-02", "MD-CHIEF-0020", "Chief Medical Officer"),
                "is_verified": True,
                "eth_address": "0x299480aE0259E42A94BCaec8530f01Ce4173428D",
                "created_at": "2026-10-26T20:09:00Z"
            },
            # Patients
            {
                "id": 7,
                "name": "Aswin Krishna",
                "email": "patient@securehealth.org",
                "password_hash": hash_password("patient"),
                "role": "patient",
                "hospital_id": "HOSP-METRO-01",
                "hospital_name": "Metro Health General Hospital",
                "specialty": "Patient",
                "license_number": None,
                "is_head_doctor": False,
                "doctor_hash": None,
                "is_verified": True,
                "eth_address": None,
                "created_at": "2026-10-26T20:10:00Z"
            }
        ]
        for u in default_users:
            self.users_cache[u["email"]] = u
            self.users_by_id[u["id"]] = u

        demo_record = {
            "record_uuid": "EHR-DEMO-001",
            "patient_id": 7,
            "doctor_id": 2,
            "patient_name": "Aswin Krishna",
            "doctor_name": "Dr. Sarah Jenkins",
            "doctor_specialty": "Cardiologist",
            "doctor_license": "MD-CARDIO-8821",
            "hospital_id": "HOSP-METRO-01",
            "hospital_name": "Metro Health General Hospital",
            "diagnosis": "Cardiovascular Assessment - Normal Sinus Rhythm",
            "clinical_metrics": {
                "age": 48,
                "resting_bp": 122,
                "cholesterol": 195,
                "max_hr": 154,
                "fasting_blood_sugar": 0,
                "angina": 0
            },
            "record_hash": "0x7a8f9c1b2e3d4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f90",
            "blockchain_tx_hash": "0x4b6d91f2c83a74e50d18293746a5b2c1d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8",
            "qr_code_url": "/static/qrcodes/EHR-DEMO-001.svg",
            "created_at": "2026-10-26T20:15:00Z"
        }
        self.ehr_cache["EHR-DEMO-001"] = demo_record

        self.audit_cache.append({
            "id": 1,
            "record_uuid": "EHR-DEMO-001",
            "action": "RECORD_CREATED_AND_SEALED",
            "status": "VERIFIED_AUTHENTIC",
            "timestamp": "2026-10-26T20:15:00Z",
            "details": "Initial authentic EHR record anchored on blockchain ledger by Dr. Sarah Jenkins (Cardiologist, Verified)."
        })

    def _get_raw_connection(self, include_db=True):
        if not self.driver:
            raise RuntimeError("Neither pymysql nor mysql-connector-python is installed")

        db_name = self.database if include_db else None

        if self.driver == "pymysql":
            return pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=db_name,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3,
                autocommit=True
            )
        else:
            import mysql.connector
            params = {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "password": self.password,
                "connection_timeout": 3,
                "autocommit": True
            }
            if db_name:
                params["database"] = db_name
            return mysql.connector.connect(**params)

    def init_database(self) -> bool:
        """Connect to MySQL, create database and tables if missing, and sync state."""
        if not self.driver:
            self.is_connected = False
            self.last_error = "No MySQL driver installed (run: pip install pymysql)"
            return False

        try:
            raw_conn = self._get_raw_connection(include_db=False)
            cursor = raw_conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            cursor.close()
            raw_conn.close()

            conn = self._get_raw_connection(include_db=True)
            cursor = conn.cursor()

            # Table 1: hospitals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hospitals (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    hospital_id VARCHAR(64) NOT NULL UNIQUE,
                    hospital_name VARCHAR(150) NOT NULL,
                    city VARCHAR(100) NOT NULL,
                    node_id VARCHAR(64) NOT NULL,
                    hospital_hash VARCHAR(66) NOT NULL,
                    eth_address VARCHAR(42) DEFAULT NULL,
                    is_registered BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_hosp_id (hospital_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Table 2: users (with doctor specialty & verification fields)
            cursor.execute("""
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
                    doctor_hash VARCHAR(66) DEFAULT NULL,
                    is_verified BOOLEAN DEFAULT TRUE,
                    eth_address VARCHAR(42) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Migrate users columns if missing
            self._ensure_column_exists(cursor, "users", "hospital_id", "VARCHAR(64) DEFAULT 'HOSP-METRO-01'")
            self._ensure_column_exists(cursor, "users", "specialty", "VARCHAR(100) DEFAULT 'General Medicine'")
            self._ensure_column_exists(cursor, "users", "license_number", "VARCHAR(50) DEFAULT NULL")
            self._ensure_column_exists(cursor, "users", "is_head_doctor", "BOOLEAN DEFAULT FALSE")
            self._ensure_column_exists(cursor, "users", "doctor_hash", "VARCHAR(66) DEFAULT NULL")
            self._ensure_column_exists(cursor, "users", "is_verified", "BOOLEAN DEFAULT TRUE")

            # Table 3: ehr_records
            cursor.execute("""
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
                    clinical_metrics JSON NOT NULL,
                    record_hash VARCHAR(66) NOT NULL,
                    blockchain_tx_hash VARCHAR(66) DEFAULT NULL,
                    qr_code_url VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_patient (patient_id),
                    INDEX idx_hash (record_hash)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            self._ensure_column_exists(cursor, "ehr_records", "doctor_specialty", "VARCHAR(100) DEFAULT 'General Medicine'")
            self._ensure_column_exists(cursor, "ehr_records", "doctor_license", "VARCHAR(50) DEFAULT NULL")
            self._ensure_column_exists(cursor, "ehr_records", "hospital_id", "VARCHAR(64) DEFAULT 'HOSP-METRO-01'")

            # Table 4: edge_model_updates
            cursor.execute("""
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Table 5: fl_rounds
            cursor.execute("""
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
            """)

            # Table 6: audit_logs
            cursor.execute("""
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
            """)

            # Seed default hospitals
            cursor.execute("SELECT COUNT(*) AS cnt FROM hospitals;")
            h_count = cursor.fetchone()["cnt"]
            if h_count == 0:
                for h in self.hospitals_cache.values():
                    cursor.execute("""
                        INSERT IGNORE INTO hospitals (id, hospital_id, hospital_name, city, node_id, hospital_hash, eth_address, is_registered)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (h["id"], h["hospital_id"], h["hospital_name"], h["city"], h["node_id"], h["hospital_hash"], h["eth_address"], h["is_registered"]))

            # Seed or update doctors
            for u in self.users_cache.values():
                cursor.execute("""
                    INSERT INTO users (id, name, email, password_hash, role, hospital_id, hospital_name, specialty, license_number, is_head_doctor, doctor_hash, is_verified, eth_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        role = VALUES(role),
                        hospital_id = VALUES(hospital_id),
                        hospital_name = VALUES(hospital_name),
                        specialty = VALUES(specialty),
                        license_number = VALUES(license_number),
                        is_head_doctor = VALUES(is_head_doctor),
                        doctor_hash = VALUES(doctor_hash),
                        is_verified = VALUES(is_verified);
                """, (
                    u["id"], u["name"], u["email"], u["password_hash"], u["role"],
                    u.get("hospital_id", "HOSP-METRO-01"), u.get("hospital_name", "Metro Health General Hospital"),
                    u.get("specialty", "General Medicine"), u.get("license_number"),
                    u.get("is_head_doctor", False), u.get("doctor_hash"), u.get("is_verified", True),
                    u.get("eth_address")
                ))

            # Sync from MySQL to in-memory cache
            self._sync_cache_from_db(cursor)

            cursor.close()
            conn.close()

            self.is_connected = True
            self.last_error = None
            return True

        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            return False

    def _ensure_column_exists(self, cursor, table_name: str, column_name: str, column_def: str):
        try:
            cursor.execute(f"""
                SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s;
            """, (self.database, table_name, column_name))
            row = cursor.fetchone()
            if row["cnt"] == 0:
                cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_def};")
        except Exception:
            pass

    def _sync_cache_from_db(self, cursor):
        try:
            # Hospitals
            cursor.execute("SELECT * FROM hospitals;")
            for row in cursor.fetchall():
                h_dict = dict(row)
                if isinstance(h_dict.get("created_at"), (datetime.date, datetime.datetime)):
                    h_dict["created_at"] = h_dict["created_at"].isoformat()
                self.hospitals_cache[h_dict["hospital_id"]] = h_dict

            # Users
            cursor.execute("SELECT * FROM users;")
            for row in cursor.fetchall():
                user_dict = dict(row)
                if isinstance(user_dict.get("created_at"), (datetime.date, datetime.datetime)):
                    user_dict["created_at"] = user_dict["created_at"].isoformat()
                self.users_cache[user_dict["email"]] = user_dict
                self.users_by_id[user_dict["id"]] = user_dict

            # EHR Records
            cursor.execute("SELECT * FROM ehr_records ORDER BY id DESC;")
            for row in cursor.fetchall():
                r = dict(row)
                if isinstance(r.get("clinical_metrics"), str):
                    try:
                        r["clinical_metrics"] = json.loads(r["clinical_metrics"])
                    except Exception:
                        pass
                if isinstance(r.get("created_at"), (datetime.date, datetime.datetime)):
                    r["created_at"] = r["created_at"].isoformat()
                self.ehr_cache[r["record_uuid"]] = r

            # Edge Model Updates
            cursor.execute("SELECT * FROM edge_model_updates ORDER BY id DESC;")
            for row in cursor.fetchall():
                u = dict(row)
                if isinstance(u.get("created_at"), (datetime.date, datetime.datetime)):
                    u["created_at"] = u["created_at"].isoformat()
                self.edge_updates_cache[u["update_uuid"]] = u

            # Audit Logs
            cursor.execute("SELECT * FROM audit_logs ORDER BY id ASC;")
            self.audit_cache = []
            for row in cursor.fetchall():
                log = dict(row)
                if isinstance(log.get("timestamp"), (datetime.date, datetime.datetime)):
                    log["timestamp"] = log["timestamp"].isoformat()
                self.audit_cache.append(log)

            # FL Rounds
            cursor.execute("SELECT * FROM fl_rounds ORDER BY round_number ASC;")
            self.fl_cache = []
            for row in cursor.fetchall():
                fl = dict(row)
                if isinstance(fl.get("timestamp"), (datetime.date, datetime.datetime)):
                    fl["timestamp"] = fl["timestamp"].isoformat()
                self.fl_cache.append(fl)

        except Exception as ex:
            print(f"[DB] Cache sync note: {ex}")

    # ==========================================
    # HOSPITAL ACCESS METHODS
    # ==========================================
    def get_all_hospitals(self) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM hospitals WHERE is_registered = TRUE ORDER BY id ASC;")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                return [dict(r) for r in rows]
            except Exception as e:
                self.last_error = str(e)
        return list(self.hospitals_cache.values())

    def get_hospital(self, hospital_id: str) -> Optional[Dict[str, Any]]:
        return self.hospitals_cache.get(hospital_id)

    def get_doctors_for_hospital(self, hospital_id: str) -> List[Dict[str, Any]]:
        doctors = [
            u for u in self.users_cache.values()
            if u.get("role") == "doctor" and u.get("hospital_id") == hospital_id
        ]
        return doctors

    def get_head_doctor_for_hospital(self, hospital_id: str) -> Optional[Dict[str, Any]]:
        for u in self.users_cache.values():
            if u.get("role") == "doctor" and u.get("hospital_id") == hospital_id and u.get("is_head_doctor"):
                return u
        # Fallback to any doctor if specific head doctor flag not set
        for u in self.users_cache.values():
            if u.get("role") == "doctor" and u.get("hospital_id") == hospital_id:
                return u
        return None

    # ==========================================
    # USER DATA ACCESS METHODS
    # ==========================================
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").strip().lower()
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE email = %s LIMIT 1;", (email,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                if row:
                    user_dict = dict(row)
                    if isinstance(user_dict.get("created_at"), (datetime.date, datetime.datetime)):
                        user_dict["created_at"] = user_dict["created_at"].isoformat()
                    self.users_cache[email] = user_dict
                    self.users_by_id[user_dict["id"]] = user_dict
                    return user_dict
            except Exception as e:
                self.last_error = str(e)
        return self.users_cache.get(email)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE id = %s LIMIT 1;", (user_id,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                if row:
                    user_dict = dict(row)
                    if isinstance(user_dict.get("created_at"), (datetime.date, datetime.datetime)):
                        user_dict["created_at"] = user_dict["created_at"].isoformat()
                    return user_dict
            except Exception as e:
                self.last_error = str(e)
        return self.users_by_id.get(user_id)

    def get_all_patients(self, hospital_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                if hospital_id:
                    cursor.execute("SELECT id, name, email, hospital_name, hospital_id FROM users WHERE role = 'patient' AND hospital_id = %s ORDER BY id ASC;", (hospital_id,))
                else:
                    cursor.execute("SELECT id, name, email, hospital_name, hospital_id FROM users WHERE role = 'patient' ORDER BY id ASC;")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                return [dict(r) for r in rows]
            except Exception as e:
                self.last_error = str(e)
        patients = [
            {"id": u["id"], "name": u["name"], "email": u["email"], "hospital_name": u.get("hospital_name"), "hospital_id": u.get("hospital_id")}
            for u in self.users_cache.values() if u.get("role") == "patient"
        ]
        if hospital_id:
            patients = [p for p in patients if p.get("hospital_id") == hospital_id]
        return patients

    get_patients_for_hospital = get_all_patients

    def create_user(self, name: str, email: str, password_hash: str, role: str = "patient",
                    hospital_id: str = "HOSP-METRO-01", hospital_name: str = "Metro Health General Hospital",
                    specialty: str = "General Medicine", license_number: str = None, eth_address: str = None) -> Dict[str, Any]:
        email = email.strip().lower()
        new_id = max(self.users_by_id.keys(), default=0) + 1
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        doctor_hash = None
        if role == "doctor":
            doc_id = f"DOC-{secrets.token_hex(4).upper()}"
            license_number = license_number or f"MD-{secrets.token_hex(3).upper()}"
            doctor_hash = compute_doctor_hash(doc_id, hospital_id, license_number, specialty)

        user_record = {
            "id": new_id,
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "hospital_id": hospital_id,
            "hospital_name": hospital_name,
            "specialty": specialty,
            "license_number": license_number,
            "is_head_doctor": False,
            "doctor_hash": doctor_hash,
            "is_verified": True,
            "eth_address": eth_address,
            "created_at": created_at
        }
        
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (name, email, password_hash, role, hospital_id, hospital_name, specialty, license_number, is_head_doctor, doctor_hash, is_verified, eth_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (name, email, password_hash, role, hospital_id, hospital_name, specialty, license_number, False, doctor_hash, True, eth_address))
                user_record["id"] = cursor.lastrowid or new_id
                cursor.close()
                conn.close()
            except Exception as e:
                self.last_error = str(e)
                print(f"[DB] Error creating user in MySQL: {e}")

        self.users_cache[email] = user_record
        self.users_by_id[user_record["id"]] = user_record
        return user_record

    # ==========================================
    # EHR RECORD DATA ACCESS METHODS
    # ==========================================
    def get_all_ehr_records(self, patient_id: Optional[int] = None, hospital_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                query = "SELECT * FROM ehr_records WHERE 1=1"
                params = []
                if patient_id:
                    query += " AND patient_id = %s"
                    params.append(patient_id)
                if hospital_id:
                    query += " AND hospital_id = %s"
                    params.append(hospital_id)
                query += " ORDER BY id DESC;"
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                records = []
                for row in rows:
                    r = dict(row)
                    if isinstance(r.get("clinical_metrics"), str):
                        try:
                            r["clinical_metrics"] = json.loads(r["clinical_metrics"])
                        except Exception:
                            pass
                    if isinstance(r.get("created_at"), (datetime.date, datetime.datetime)):
                        r["created_at"] = r["created_at"].isoformat()
                    records.append(r)
                return records
            except Exception as e:
                self.last_error = str(e)

        records = list(self.ehr_cache.values())
        if patient_id:
            records = [r for r in records if str(r.get("patient_id")) == str(patient_id)]
        if hospital_id:
            records = [r for r in records if r.get("hospital_id") == hospital_id]
        return sorted(records, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_ehr_record(self, record_uuid: str) -> Optional[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ehr_records WHERE record_uuid = %s LIMIT 1;", (record_uuid,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                if row:
                    r = dict(row)
                    if isinstance(r.get("clinical_metrics"), str):
                        try:
                            r["clinical_metrics"] = json.loads(r["clinical_metrics"])
                        except Exception:
                            pass
                    if isinstance(r.get("created_at"), (datetime.date, datetime.datetime)):
                        r["created_at"] = r["created_at"].isoformat()
                    self.ehr_cache[record_uuid] = r
                    return r
            except Exception as e:
                self.last_error = str(e)
        return self.ehr_cache.get(record_uuid)

    def save_ehr_record(self, record: Dict[str, Any]) -> bool:
        uuid_str = record.get("record_uuid")
        self.ehr_cache[uuid_str] = record
        
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                metrics_json = json.dumps(record.get("clinical_metrics", {}))
                cursor.execute("""
                    INSERT INTO ehr_records 
                    (record_uuid, patient_id, doctor_id, patient_name, doctor_name, doctor_specialty, doctor_license, hospital_id, hospital_name, diagnosis, clinical_metrics, record_hash, blockchain_tx_hash, qr_code_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        diagnosis = VALUES(diagnosis),
                        clinical_metrics = VALUES(clinical_metrics),
                        record_hash = VALUES(record_hash),
                        blockchain_tx_hash = VALUES(blockchain_tx_hash),
                        qr_code_url = VALUES(qr_code_url);
                """, (
                    uuid_str, record.get("patient_id"), record.get("doctor_id"),
                    record.get("patient_name"), record.get("doctor_name"),
                    record.get("doctor_specialty", "General Medicine"), record.get("doctor_license"),
                    record.get("hospital_id", "HOSP-METRO-01"), record.get("hospital_name"),
                    record.get("diagnosis"), metrics_json, record.get("record_hash"),
                    record.get("blockchain_tx_hash"), record.get("qr_code_url")
                ))
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"[DB] Error saving EHR to MySQL: {e}")
                return False
        return True

    # ==========================================
    # EDGE MODEL UPDATE & HEAD DOCTOR APPROVAL METHODS
    # ==========================================
    def save_edge_model_update(self, update_data: Dict[str, Any]) -> Dict[str, Any]:
        update_uuid = update_data.get("update_uuid") or f"UPDATE-{secrets.token_hex(6).upper()}"
        update_data["update_uuid"] = update_uuid
        self.edge_updates_cache[update_uuid] = update_data

        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO edge_model_updates
                    (update_uuid, round_number, hospital_id, hospital_name, doctor_id, doctor_name, doctor_specialty, model_hash, samples_count, local_loss, local_accuracy, dp_epsilon, noise_sigma, head_doctor_id, head_doctor_name, head_doctor_signature_hash, approval_status, blockchain_tx_hash, central_verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        head_doctor_id = VALUES(head_doctor_id),
                        head_doctor_name = VALUES(head_doctor_name),
                        head_doctor_signature_hash = VALUES(head_doctor_signature_hash),
                        approval_status = VALUES(approval_status),
                        blockchain_tx_hash = VALUES(blockchain_tx_hash),
                        central_verification_status = VALUES(central_verification_status);
                """, (
                    update_uuid, update_data.get("round_number", 1),
                    update_data.get("hospital_id", "HOSP-METRO-01"), update_data.get("hospital_name", "Metro Health"),
                    update_data.get("doctor_id"), update_data.get("doctor_name"), update_data.get("doctor_specialty", "Doctor"),
                    update_data.get("model_hash"), update_data.get("samples_count", 1),
                    update_data.get("local_loss", 0.0), update_data.get("local_accuracy", 0.0),
                    update_data.get("dp_epsilon", 1.0), update_data.get("noise_sigma", 0.24),
                    update_data.get("head_doctor_id"), update_data.get("head_doctor_name"),
                    update_data.get("head_doctor_signature_hash"), update_data.get("approval_status", "PENDING_REVIEW"),
                    update_data.get("blockchain_tx_hash"), update_data.get("central_verification_status", "PENDING")
                ))
                cursor.close()
                conn.close()
            except Exception as e:
                self.last_error = str(e)
                print(f"[DB] Error saving edge update: {e}")

        return update_data

    def get_latest_edge_update(self, hospital_id: str) -> Optional[Dict[str, Any]]:
        updates = [u for u in self.edge_updates_cache.values() if u.get("hospital_id") == hospital_id]
        if updates:
            return sorted(updates, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        return None

    # ==========================================
    # AUDIT LOG & FL ROUND METHODS
    # ==========================================
    def save_audit_log(self, record_uuid: str, action: str, status: str = "VERIFIED_AUTHENTIC",
                       details: str = "", performed_by: Optional[int] = None, tx_hash: Optional[str] = None) -> Dict[str, Any]:
        log_id = len(self.audit_cache) + 1
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = {
            "id": log_id,
            "record_uuid": record_uuid,
            "action": action,
            "status": status,
            "performed_by": performed_by,
            "blockchain_tx_hash": tx_hash,
            "details": details,
            "timestamp": now_iso
        }
        self.audit_cache.append(log_entry)

        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_logs (record_uuid, action, status, performed_by, blockchain_tx_hash, details)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (record_uuid, action, status, performed_by, tx_hash, details))
                log_entry["id"] = cursor.lastrowid or log_id
                cursor.close()
                conn.close()
            except Exception as e:
                self.last_error = str(e)

        return log_entry

    def save_fl_round(self, round_number: int, global_model_hash: str, accuracy: float,
                      precision_score: Optional[float] = None, recall_score: Optional[float] = None,
                      f1_score: Optional[float] = None, tx_hash: Optional[str] = None,
                      participating_nodes: int = 4) -> Dict[str, Any]:
        fl_entry = {
            "round_number": round_number,
            "global_model_hash": global_model_hash,
            "accuracy": accuracy,
            "precision_score": precision_score,
            "recall_score": recall_score,
            "f1_score": f1_score,
            "blockchain_tx_hash": tx_hash,
            "participating_nodes": participating_nodes,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.fl_cache.append(fl_entry)

        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO fl_rounds (round_number, global_model_hash, accuracy, precision_score, recall_score, f1_score, blockchain_tx_hash, participating_nodes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (round_number, global_model_hash, accuracy, precision_score, recall_score, f1_score, tx_hash, participating_nodes))
                cursor.close()
                conn.close()
            except Exception as e:
                self.last_error = str(e)

        return fl_entry

    def get_fl_history(self) -> List[Dict[str, Any]]:
        return self.fl_cache

    def get_status(self) -> Dict[str, Any]:
        if not self.is_connected:
            self.init_database()

        status = {
            "connected": self.is_connected,
            "driver": self.driver,
            "mode": "MySQL Persistent Database" if self.is_connected else "Resilient In-Memory Fallback",
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "total_hospitals": len(self.hospitals_cache),
            "total_users": len(self.users_cache),
            "total_records": len(self.ehr_cache),
            "total_audit_logs": len(self.audit_cache),
            "total_fl_rounds": len(self.fl_cache),
            "last_error": self.last_error
        }
        return status

# Singleton instance
db_service = DatabaseService()
