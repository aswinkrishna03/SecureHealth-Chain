"""
SecureHealth Chain - MySQL Database Service
Dual-Mode Database Architecture:
- Primary: Real-time MySQL persistence (users, ehr_records, fl_rounds, audit_logs)
- Resilient Fallback: In-memory store when MySQL is offline / unreachable
Seamlessly adapts to XAMPP, WampServer, Docker, or standalone MySQL installations.
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
                # Werkzeug legacy demo format fallback: pbkdf2:sha256:rounds$salt$digest
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
        self.users_cache: Dict[str, Dict[str, Any]] = {}
        self.users_by_id: Dict[int, Dict[str, Any]] = {}
        self.ehr_cache: Dict[str, Dict[str, Any]] = {}
        self.audit_cache: List[Dict[str, Any]] = []
        self.fl_cache: List[Dict[str, Any]] = []
        
        # Populate initial default records for fallback
        self._seed_in_memory_defaults()
        
        # Attempt MySQL connection
        self.init_database()

    def _seed_in_memory_defaults(self):
        """Seed clean in-memory defaults in case MySQL is offline."""
        default_users = [
            {
                "id": 1,
                "name": "System Administrator",
                "email": "admin@securehealth.org",
                "password_hash": hash_password("admin"),
                "role": "admin",
                "hospital_name": "Health Network HQ",
                "eth_address": None,
                "created_at": "2026-10-26T20:00:00Z"
            },
            {
                "id": 2,
                "name": "Dr. Sarah Jenkins",
                "email": "doctor@securehealth.org",
                "password_hash": hash_password("doctor"),
                "role": "doctor",
                "hospital_name": "Metro Health General Hospital",
                "eth_address": None,
                "created_at": "2026-10-26T20:05:00Z"
            },
            {
                "id": 3,
                "name": "Aswin Krishna",
                "email": "patient@securehealth.org",
                "password_hash": hash_password("patient"),
                "role": "patient",
                "hospital_name": "Metro Health General Hospital",
                "eth_address": None,
                "created_at": "2026-10-26T20:10:00Z"
            }
        ]
        for u in default_users:
            self.users_cache[u["email"]] = u
            self.users_by_id[u["id"]] = u

        demo_record = {
            "record_uuid": "EHR-DEMO-001",
            "patient_id": 3,
            "doctor_id": 2,
            "patient_name": "Aswin Krishna",
            "doctor_name": "Dr. Sarah Jenkins",
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
            "details": "Initial authentic EHR record anchored on blockchain ledger."
        })

    def _get_raw_connection(self, include_db=True):
        """Create a new raw database connection."""
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
            # Step 1: Connect to server without database and ensure DB exists
            raw_conn = self._get_raw_connection(include_db=False)
            cursor = raw_conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            cursor.close()
            raw_conn.close()

            # Step 2: Connect to the specific database and create tables
            conn = self._get_raw_connection(include_db=True)
            cursor = conn.cursor()

            # Table 1: users
            cursor.execute("""
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
            """)

            # Table 2: ehr_records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ehr_records (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    record_uuid VARCHAR(64) NOT NULL UNIQUE,
                    patient_id INT NOT NULL,
                    doctor_id INT NOT NULL,
                    patient_name VARCHAR(100) DEFAULT NULL,
                    doctor_name VARCHAR(100) DEFAULT NULL,
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

            # Table 3: fl_rounds
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
                    participating_nodes INT DEFAULT 3,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Table 4: audit_logs
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

            # Seed default users if empty
            cursor.execute("SELECT COUNT(*) AS cnt FROM users;")
            row = cursor.fetchone()
            count = row["cnt"] if isinstance(row, dict) else row[0]
            if count == 0:
                for u in self.users_cache.values():
                    cursor.execute("""
                        INSERT IGNORE INTO users (id, name, email, password_hash, role, hospital_name, eth_address)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """, (u["id"], u["name"], u["email"], u["password_hash"], u["role"], u["hospital_name"], u.get("eth_address")))

            # Seed demo EHR record if empty
            cursor.execute("SELECT COUNT(*) AS cnt FROM ehr_records;")
            row = cursor.fetchone()
            count = row["cnt"] if isinstance(row, dict) else row[0]
            if count == 0:
                demo = self.ehr_cache["EHR-DEMO-001"]
                cursor.execute("""
                    INSERT IGNORE INTO ehr_records (record_uuid, patient_id, doctor_id, patient_name, doctor_name, hospital_name, diagnosis, clinical_metrics, record_hash, blockchain_tx_hash, qr_code_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    demo["record_uuid"], demo["patient_id"], demo["doctor_id"],
                    demo["patient_name"], demo["doctor_name"], demo["hospital_name"],
                    demo["diagnosis"], json.dumps(demo["clinical_metrics"]),
                    demo["record_hash"], demo["blockchain_tx_hash"], demo["qr_code_url"]
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

    def _sync_cache_from_db(self, cursor):
        """Read users, ehr records, audit logs, and fl rounds into fast cache."""
        try:
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
            print(f"[DB] Cache sync warning: {ex}")

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

    def get_all_patients(self) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, email, hospital_name FROM users WHERE role = 'patient' ORDER BY id ASC;")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                return [dict(r) for r in rows]
            except Exception as e:
                self.last_error = str(e)
        return [
            {"id": u["id"], "name": u["name"], "email": u["email"], "hospital_name": u.get("hospital_name")}
            for u in self.users_cache.values() if u.get("role") == "patient"
        ]

    def create_user(self, name: str, email: str, password_hash: str, role: str = "patient",
                    hospital_name: str = "Metro Health General Hospital", eth_address: str = None) -> Dict[str, Any]:
        email = email.strip().lower()
        new_id = max(self.users_by_id.keys(), default=0) + 1
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        user_record = {
            "id": new_id,
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "hospital_name": hospital_name,
            "eth_address": eth_address,
            "created_at": created_at
        }
        
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (name, email, password_hash, role, hospital_name, eth_address)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (name, email, password_hash, role, hospital_name, eth_address))
                user_record["id"] = cursor.lastrowid or new_id
                cursor.close()
                conn.close()
            except Exception as e:
                self.last_error = str(e)
                print(f"[DB] Error creating user in MySQL: {e}")

        # Always update memory cache
        self.users_cache[email] = user_record
        self.users_by_id[user_record["id"]] = user_record
        return user_record

    # ==========================================
    # EHR RECORD DATA ACCESS METHODS
    # ==========================================
    def get_all_ehr_records(self, patient_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                if patient_id:
                    cursor.execute("SELECT * FROM ehr_records WHERE patient_id = %s ORDER BY id DESC;", (patient_id,))
                else:
                    cursor.execute("SELECT * FROM ehr_records ORDER BY id DESC;")
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
                    (record_uuid, patient_id, doctor_id, patient_name, doctor_name, hospital_name, diagnosis, clinical_metrics, record_hash, blockchain_tx_hash, qr_code_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        diagnosis = VALUES(diagnosis),
                        clinical_metrics = VALUES(clinical_metrics),
                        record_hash = VALUES(record_hash),
                        blockchain_tx_hash = VALUES(blockchain_tx_hash),
                        qr_code_url = VALUES(qr_code_url);
                """, (
                    uuid_str, record.get("patient_id"), record.get("doctor_id"),
                    record.get("patient_name"), record.get("doctor_name"), record.get("hospital_name"),
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

    def tamper_ehr_record(self, record_uuid: str, new_diagnosis: str = "[TAMPERED DATA] Malicious Alteration Detected!", new_cholesterol: int = 999) -> bool:
        """Modify record in database to demonstrate cryptographic tamper detection."""
        if record_uuid in self.ehr_cache:
            self.ehr_cache[record_uuid]["diagnosis"] = new_diagnosis
            if "clinical_metrics" in self.ehr_cache[record_uuid] and isinstance(self.ehr_cache[record_uuid]["clinical_metrics"], dict):
                self.ehr_cache[record_uuid]["clinical_metrics"]["cholesterol"] = new_cholesterol

        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT clinical_metrics FROM ehr_records WHERE record_uuid = %s;", (record_uuid,))
                row = cursor.fetchone()
                if row:
                    metrics = row["clinical_metrics"]
                    if isinstance(metrics, str):
                        metrics = json.loads(metrics)
                    metrics["cholesterol"] = new_cholesterol
                    cursor.execute("""
                        UPDATE ehr_records 
                        SET diagnosis = %s, clinical_metrics = %s 
                        WHERE record_uuid = %s;
                    """, (new_diagnosis, json.dumps(metrics), record_uuid))
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                self.last_error = str(e)
                return False
        return True

    # ==========================================
    # AUDIT LOG DATA ACCESS METHODS
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

    def get_all_audit_logs(self) -> List[Dict[str, Any]]:
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100;")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                logs = []
                for row in rows:
                    l = dict(row)
                    if isinstance(l.get("timestamp"), (datetime.date, datetime.datetime)):
                        l["timestamp"] = l["timestamp"].isoformat()
                    logs.append(l)
                return logs
            except Exception as e:
                self.last_error = str(e)
        return list(reversed(self.audit_cache))

    # ==========================================
    # FEDERATED LEARNING AUDIT LOG METHODS
    # ==========================================
    def save_fl_round(self, round_number: int, global_model_hash: str, accuracy: float,
                      precision_score: Optional[float] = None, recall_score: Optional[float] = None,
                      f1_score: Optional[float] = None, tx_hash: Optional[str] = None,
                      participating_nodes: int = 3) -> Dict[str, Any]:
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
        if self.is_connected:
            try:
                conn = self._get_raw_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM fl_rounds ORDER BY round_number ASC;")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                rounds = []
                for row in rows:
                    r = dict(row)
                    if isinstance(r.get("timestamp"), (datetime.date, datetime.datetime)):
                        r["timestamp"] = r["timestamp"].isoformat()
                    rounds.append(r)
                return rounds
            except Exception as e:
                self.last_error = str(e)
        return self.fl_cache

    # ==========================================
    # HEALTH / DIAGNOSTIC STATUS
    # ==========================================
    def get_status(self) -> Dict[str, Any]:
        # Try reconnecting if previously failed
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
            "total_users": len(self.users_cache),
            "total_records": len(self.ehr_cache),
            "total_audit_logs": len(self.audit_cache),
            "total_fl_rounds": len(self.fl_cache),
            "last_error": self.last_error
        }
        return status

# Singleton instance
db_service = DatabaseService()

if __name__ == "__main__":
    print("=" * 70)
    print(" [*] SECUREHEALTH CHAIN: MYSQL DATABASE SERVICE DIAGNOSTIC")
    print("=" * 70)
    stat = db_service.get_status()
    print(f"Driver Detected:  {stat['driver']}")
    print(f"Connection Host:  {stat['host']}:{stat['port']}")
    print(f"Database Target:  {stat['database']}")
    print(f"Connection User:  {stat['user']}")
    print(f"Current Mode:     {stat['mode']}")
    print(f"Is Connected:     {stat['connected']}")
    if not stat['connected']:
        print(f"Offline Notice:   {stat['last_error']}")
        print("-> To connect live MySQL:")
        print("   1. Open XAMPP / MySQL Service / MySQL Workbench and start MySQL.")
        print("   2. Verify MySQL is listening on port 3306.")
        print("   3. Configure credentials in .env if your root user has a password.")
    else:
        print(f"Users in DB:      {stat['total_users']}")
        print(f"EHR Records:      {stat['total_records']}")
        print(f"Audit Logs:       {stat['total_audit_logs']}")
        print("MySQL Database is healthy and active!")
    print("=" * 70)
