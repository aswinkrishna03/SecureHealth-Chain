"""
Live Ethereum Blockchain Ledger & Smart Contract Service for SecureHealth Chain.

Integrates with a live Ganache local Ethereum testnet node and the deployed
SecureHealthRegistry.sol smart contract using web3.py.
Handles Multi-Hospital node registration, Doctor credential verification,
and Head-Doctor approved Federated Learning model commitments.
"""

import os
import sys
import time
import hashlib
import json
import datetime
from typing import List, Dict, Any, Optional

try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False

GANACHE_RPC_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:7545")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEPLOYED_CONTRACT_PATH = os.path.join(PROJECT_ROOT, "blockchain", "build", "deployed_contract.json")

def datetime_from_timestamp(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

def to_bytes32(val: str) -> bytes:
    """Safely converts a hex string or arbitrary string to 32 bytes for Solidity bytes32."""
    clean = val.replace("0x", "").strip()
    if len(clean) == 64:
        try:
            return bytes.fromhex(clean)
        except ValueError:
            pass
    return hashlib.sha256(val.encode("utf-8")).digest()

class Transaction:
    def __init__(self, tx_type: str, sender: str, payload: Dict[str, Any], tx_hash: Optional[str] = None):
        self.tx_type = tx_type
        self.sender = sender
        self.payload = payload
        self.timestamp = time.time()
        self.tx_hash = tx_hash or self.compute_hash()

    def compute_hash(self) -> str:
        data = f"{self.tx_type}:{self.sender}:{json.dumps(self.payload, sort_keys=True)}:{self.timestamp}"
        return "0x" + hashlib.sha256(data.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "tx_type": self.tx_type,
            "sender": self.sender,
            "payload": self.payload,
            "timestamp": datetime_from_timestamp(self.timestamp)
        }

class Block:
    def __init__(self, index: int, previous_hash: str, transactions: List[Transaction], validator: str = "Ganache-Validator-PoA"):
        self.index = index
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.timestamp = time.time()
        self.validator = validator
        self.hash = self.compute_block_hash()

    def compute_block_hash(self) -> str:
        tx_hashes = "".join(tx.tx_hash for tx in self.transactions)
        content = f"{self.index}{self.previous_hash}{tx_hashes}{self.timestamp}{self.validator}"
        return "0x" + hashlib.sha256(content.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_number": self.index,
            "previous_hash": self.previous_hash,
            "block_hash": self.hash,
            "validator": self.validator,
            "transactions_count": len(self.transactions),
            "transactions": [tx.to_dict() for tx in self.transactions],
            "timestamp": datetime_from_timestamp(self.timestamp)
        }

class BlockchainLedger:
    def __init__(self):
        self.w3: Optional[Web3] = None
        self.contract = None
        self.contract_address: Optional[str] = None
        self.contract_abi: Optional[list] = None
        self.deployer_account: Optional[str] = None
        
        # Local State Caches (Mirrors on-chain state for fast querying)
        self.registered_hospitals: Dict[str, Dict[str, Any]] = {}
        self.registered_doctors: Dict[str, Dict[str, Any]] = {}
        self.ehr_registry: Dict[str, Dict[str, Any]] = {}
        self.fl_round_updates: Dict[int, List[Dict[str, Any]]] = {}
        self.global_models: Dict[int, str] = {}
        
        # In-memory blocks for resilient fallback
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self._init_genesis_block()
        
        # Attempt connecting to live Ganache
        self._init_live_web3()

    def _init_genesis_block(self):
        genesis_tx = Transaction(
            tx_type="GENESIS",
            sender="0x0000000000000000000000000000000000000000",
            payload={"system": "SecureHealth Chain Multi-Hospital EVM Genesis", "timestamp": time.time()}
        )
        genesis_block = Block(index=0, previous_hash="0x0000000000000000000000000000000000000000000000000000000000000000", transactions=[genesis_tx])
        self.chain.append(genesis_block)

    def _init_live_web3(self) -> bool:
        if not HAS_WEB3:
            return False

        try:
            self.w3 = Web3(Web3.HTTPProvider(GANACHE_RPC_URL))
            if not self.w3.is_connected():
                return False

            if not os.path.isfile(DEPLOYED_CONTRACT_PATH):
                return False

            with open(DEPLOYED_CONTRACT_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
                self.contract_address = meta.get("contractAddress")
                self.contract_abi = meta.get("abi")
                self.deployer_account = meta.get("deployer")

            if not self.contract_address or not self.contract_abi:
                return False

            self.contract_address = Web3.to_checksum_address(self.contract_address)
            self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.contract_abi)

            if not self.deployer_account and len(self.w3.eth.accounts) > 0:
                self.deployer_account = self.w3.eth.accounts[0]

            # Auto-bootstrap on-chain identity records
            self.bootstrap_on_chain_identities()
            return True
        except Exception as e:
            print(f"[BlockchainLedger Note] Ganache not connected ({e}), using resilient local ledger.")
            return False

    def check_live_ganache(self) -> bool:
        if self.w3 and self.w3.is_connected() and self.contract:
            return True
        return self._init_live_web3()

    def mine_pending(self) -> Block:
        prev_hash = self.chain[-1].hash if self.chain else "0x0"
        block = Block(
            index=len(self.chain),
            previous_hash=prev_hash,
            transactions=list(self.pending_transactions),
            validator="SecureHealth-MultiHosp-EVM"
        )
        self.chain.append(block)
        self.pending_transactions = []
        return block

    # ==========================================
    # 1. HOSPITAL ON-CHAIN REGISTRATION & CHECK
    # ==========================================
    def register_hospital_on_chain(self, hospital_id: str, hospital_name: str, hospital_hash: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(hospital_hash)
        sender = self.deployer_account or "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51"

        if is_live and self.contract and self.w3:
            try:
                # Check if already registered
                is_reg, _, _, _ = self.contract.functions.isHospitalRegistered(hospital_id).call()
                if not is_reg:
                    tx_call = self.contract.functions.registerHospital(hospital_id, hospital_name, b32_hash)
                    tx_hash = tx_call.transact({'from': sender})
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                else:
                    tx_hex = "0xALREADY_REGISTERED_ON_CHAIN"

                self.registered_hospitals[hospital_id] = {
                    "hospital_id": hospital_id,
                    "hospital_name": hospital_name,
                    "hospital_hash": hospital_hash,
                    "is_registered": True
                }
                return {"success": True, "tx_hash": tx_hex, "on_chain": True}
            except Exception as e:
                print(f"[Blockchain] registerHospital on-chain note: {e}")

        # Fallback
        self.registered_hospitals[hospital_id] = {
            "hospital_id": hospital_id,
            "hospital_name": hospital_name,
            "hospital_hash": hospital_hash,
            "is_registered": True
        }
        return {"success": True, "tx_hash": "0xLOCAL_FALLBACK_TX", "on_chain": False}

    def verify_hospital_on_chain(self, hospital_id: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        if is_live and self.contract:
            try:
                is_reg, h_name, h_hash, node_addr = self.contract.functions.isHospitalRegistered(hospital_id).call()
                return {
                    "is_registered": is_reg,
                    "hospital_name": h_name,
                    "hospital_hash": "0x" + h_hash.hex(),
                    "node_address": node_addr,
                    "on_chain": True
                }
            except Exception as e:
                print(f"[Blockchain] verify_hospital note: {e}")

        h = self.registered_hospitals.get(hospital_id)
        if h:
            return {"is_registered": True, "hospital_name": h["hospital_name"], "hospital_hash": h["hospital_hash"], "on_chain": False}
        return {"is_registered": False, "on_chain": False}

    # ==========================================
    # 2. DOCTOR ON-CHAIN REGISTRATION & CHECK
    # ==========================================
    def register_doctor_on_chain(self, doctor_id: str, hospital_id: str, doctor_name: str,
                                 specialty: str, license_number: str, doctor_hash: str,
                                 is_head_doctor: bool = False) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(doctor_hash)
        sender = self.deployer_account or "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51"

        if is_live and self.contract and self.w3:
            try:
                # Ensure hospital is registered first
                is_h_reg, _, _, _ = self.contract.functions.isHospitalRegistered(hospital_id).call()
                if not is_h_reg:
                    self.register_hospital_on_chain(hospital_id, hospital_id, doctor_hash)

                is_doc_reg, _, _, _, _, _ = self.contract.functions.isDoctorVerified(doctor_id, hospital_id).call()
                if not is_doc_reg:
                    tx_call = self.contract.functions.registerDoctor(
                        doctor_id, hospital_id, doctor_name, specialty, license_number, b32_hash, is_head_doctor
                    )
                    tx_hash = tx_call.transact({'from': sender})
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                else:
                    tx_hex = "0xDOCTOR_ALREADY_ON_CHAIN"

                self.registered_doctors[doctor_id] = {
                    "doctor_id": doctor_id,
                    "hospital_id": hospital_id,
                    "doctor_name": doctor_name,
                    "specialty": specialty,
                    "license_number": license_number,
                    "doctor_hash": doctor_hash,
                    "is_head_doctor": is_head_doctor,
                    "is_verified": True
                }
                return {"success": True, "tx_hash": tx_hex, "on_chain": True}
            except Exception as e:
                print(f"[Blockchain] registerDoctor on-chain note: {e}")

        self.registered_doctors[doctor_id] = {
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "doctor_name": doctor_name,
            "specialty": specialty,
            "license_number": license_number,
            "doctor_hash": doctor_hash,
            "is_head_doctor": is_head_doctor,
            "is_verified": True
        }
        return {"success": True, "tx_hash": "0xLOCAL_FALLBACK_TX", "on_chain": False}

    def verify_doctor_on_chain(self, doctor_id: str, hospital_id: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        if is_live and self.contract:
            try:
                is_ver, d_name, spec, lic, d_hash, is_head = self.contract.functions.isDoctorVerified(doctor_id, hospital_id).call()
                return {
                    "is_verified": is_ver,
                    "doctor_name": d_name,
                    "specialty": spec,
                    "license_number": lic,
                    "doctor_hash": "0x" + d_hash.hex(),
                    "is_head_doctor": is_head,
                    "on_chain": True
                }
            except Exception as e:
                print(f"[Blockchain] verify_doctor note: {e}")

        d = self.registered_doctors.get(doctor_id)
        if d and d["hospital_id"] == hospital_id:
            return {
                "is_verified": True,
                "doctor_name": d["doctor_name"],
                "specialty": d["specialty"],
                "license_number": d["license_number"],
                "doctor_hash": d["doctor_hash"],
                "is_head_doctor": d["is_head_doctor"],
                "on_chain": False
            }
        return {"is_verified": False, "on_chain": False}

    def bootstrap_on_chain_identities(self):
        """Ensures all standard hospitals and doctors exist on Ethereum Ganache."""
        hospitals_to_seed = [
            ("HOSP-METRO-01", "Metro Health General Hospital", "0x0111111111111111111111111111111111111111111111111111111111111111"),
            ("HOSP-APOLLO-02", "Apollo Healthcare Network", "0x0222222222222222222222222222222222222222222222222222222222222222"),
            ("HOSP-ASTER-03", "Aster Medcity Silo", "0x0333333333333333333333333333333333333333333333333333333333333333"),
            ("HOSP-CITY-04", "City Central Clinic", "0x0444444444444444444444444444444444444444444444444444444444444444")
        ]
        for hid, hname, hhash in hospitals_to_seed:
            self.register_hospital_on_chain(hid, hname, hhash)

        doctors_to_seed = [
            ("DOC-METRO-01", "HOSP-METRO-01", "Dr. Sarah Jenkins", "Cardiologist", "MD-CARDIO-8821", "0x8a3f91b2c4e567890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-2", "HOSP-METRO-01", "Dr. Sarah Jenkins", "Cardiologist", "MD-CARDIO-8821", "0x8a3f91b2c4e567890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-METRO-02", "HOSP-METRO-01", "Dr. Alex Morgan", "General Physician", "MD-INT-4412", "0x7b2e81a1c3d4567890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-3", "HOSP-METRO-01", "Dr. Alex Morgan", "General Physician", "MD-INT-4412", "0x7b2e81a1c3d4567890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-METRO-HEAD", "HOSP-METRO-01", "Dr. Marcus Vance (CMO)", "Chief Medical Officer", "MD-CHIEF-0010", "0x9c4e02b3d5e67890123456789abcdef0123456789abcdef0123456789abcdef", True),
            ("DOC-4", "HOSP-METRO-01", "Dr. Marcus Vance (CMO)", "Chief Medical Officer", "MD-CHIEF-0010", "0x9c4e02b3d5e67890123456789abcdef0123456789abcdef0123456789abcdef", True),
            ("DOC-APOLLO-01", "HOSP-APOLLO-02", "Dr. Priya Nair", "Cardiologist", "MD-CARDIO-5510", "0x5d1c92a2b4e67890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-5", "HOSP-APOLLO-02", "Dr. Priya Nair", "Cardiologist", "MD-CARDIO-5510", "0x5d1c92a2b4e67890123456789abcdef0123456789abcdef0123456789abcdef", False),
            ("DOC-APOLLO-HEAD", "HOSP-APOLLO-02", "Dr. Elena Rostova (CMO)", "Chief Medical Officer", "MD-CHIEF-0020", "0x6e2d03b4c5e67890123456789abcdef0123456789abcdef0123456789abcdef", True),
            ("DOC-6", "HOSP-APOLLO-02", "Dr. Elena Rostova (CMO)", "Chief Medical Officer", "MD-CHIEF-0020", "0x6e2d03b4c5e67890123456789abcdef0123456789abcdef0123456789abcdef", True)
        ]
        for doc in doctors_to_seed:
            self.register_doctor_on_chain(doc[0], doc[1], doc[2], doc[3], doc[4], doc[5], doc[6])

    # ==========================================
    # 3. EHR RECORD ANCHORING & VERIFICATION
    # ==========================================
    def register_ehr_record(self, record_uuid: str, record_hash: str,
                            doctor_id: str = "DOC-METRO-01",
                            hospital_id: str = "HOSP-METRO-01",
                            doctor_address: str = "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51") -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(record_hash)
        sender = self.deployer_account or doctor_address

        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.registerEHR(record_uuid, b32_hash, doctor_id, hospital_id)
                tx_hash = tx_call.transact({'from': sender, 'gas': 2000000})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                block_hex = "0x" + receipt.blockHash.hex().replace("0x", "")

                self.ehr_registry[record_uuid] = {
                    "record_hash": record_hash,
                    "recorded_by": sender,
                    "doctor_id": doctor_id,
                    "hospital_id": hospital_id,
                    "block_number": receipt.blockNumber,
                    "tx_hash": tx_hex,
                    "timestamp": time.time(),
                    "on_chain": True
                }

                tx_obj = Transaction(
                    tx_type="REGISTER_EHR",
                    sender=sender,
                    payload={"record_uuid": record_uuid, "record_hash": record_hash, "doctor_id": doctor_id, "hospital_id": hospital_id, "on_chain": True},
                    tx_hash=tx_hex
                )
                self.pending_transactions.append(tx_obj)
                self.mine_pending()

                return {
                    "success": True,
                    "tx_hash": tx_hex,
                    "block_number": receipt.blockNumber,
                    "block_hash": block_hex,
                    "consensus": "Ethereum EVM (Ganache Live)",
                    "storage_mode": "ethereum_smart_contract",
                    "contract_address": self.contract_address,
                    "is_live_ganache": True,
                    "gas_used": receipt.gasUsed
                }
            except Exception as e:
                print(f"[Blockchain Error] Live registerEHR failed ({e}), using fallback ledger.")

        tx = Transaction(
            tx_type="REGISTER_EHR",
            sender=doctor_address,
            payload={"record_uuid": record_uuid, "record_hash": record_hash, "doctor_id": doctor_id, "hospital_id": hospital_id}
        )
        self.pending_transactions.append(tx)
        mined_block = self.mine_pending()

        self.ehr_registry[record_uuid] = {
            "record_hash": record_hash,
            "recorded_by": doctor_address,
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "block_number": mined_block.index,
            "tx_hash": tx.tx_hash,
            "timestamp": tx.timestamp,
            "on_chain": False
        }

        return {
            "success": True,
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index,
            "block_hash": mined_block.hash,
            "consensus": "In-memory demo ledger",
            "storage_mode": "in_memory",
            "contract_address": self.contract_address,
            "is_live_ganache": False
        }

    def verify_ehr_record(self, record_uuid: str, incoming_hash: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_incoming = to_bytes32(incoming_hash)

        if is_live and self.contract:
            try:
                is_valid, timestamp, recorded_by, doc_id, hosp_id = self.contract.functions.verifyEHR(record_uuid, b32_incoming).call()
                stored_hash_bytes, on_chain_recorder, on_chain_ts = self.contract.functions.getEHR(record_uuid).call()
                stored_hash_hex = "0x" + stored_hash_bytes.hex()
                
                cached = self.ehr_registry.get(record_uuid, {})
                block_num = cached.get("block_number", 0)
                tx_hash = cached.get("tx_hash", "0x0000000000000000000000000000000000000000")

                exists = (recorded_by != "0x0000000000000000000000000000000000000000")
                if exists:
                    return {
                        "exists": True,
                        "is_valid": is_valid,
                        "stored_hash": stored_hash_hex,
                        "incoming_hash": incoming_hash,
                        "block_number": block_num,
                        "tx_hash": tx_hash,
                        "recorded_by": recorded_by,
                        "doctor_id": doc_id,
                        "hospital_id": hosp_id,
                        "timestamp": datetime_from_timestamp(timestamp if timestamp > 0 else time.time()),
                        "tamper_status": "AUTHENTIC" if is_valid else "TAMPER_DETECTED",
                        "verification_engine": "Ethereum Smart Contract (Ganache)"
                    }
            except Exception as e:
                print(f"[Blockchain Error] Live verifyEHR failed ({e}), using fallback verification.")

        if record_uuid not in self.ehr_registry:
            return {"exists": False, "is_valid": False, "message": "Record not found on blockchain"}
        
        entry = self.ehr_registry[record_uuid]
        clean_stored = entry["record_hash"].replace("0x", "").lower()
        clean_in = incoming_hash.replace("0x", "").lower()
        is_valid = (clean_stored == clean_in)

        return {
            "exists": True,
            "is_valid": is_valid,
            "stored_hash": entry["record_hash"],
            "incoming_hash": incoming_hash,
            "block_number": entry["block_number"],
            "tx_hash": entry["tx_hash"],
            "recorded_by": entry["recorded_by"],
            "doctor_id": entry.get("doctor_id", "DOC-METRO-01"),
            "hospital_id": entry.get("hospital_id", "HOSP-METRO-01"),
            "timestamp": datetime_from_timestamp(entry["timestamp"]),
            "tamper_status": "AUTHENTIC" if is_valid else "TAMPER_DETECTED",
            "verification_engine": "Local Ledger Engine"
        }

    # ==========================================
    # 4. MULTI-HOSPITAL & HEAD-DOCTOR MODEL COMMITMENT
    # ==========================================
    def submit_verified_fl_model_update(self, round_num: int, hospital_id: str,
                                        doctor_id: str, head_doctor_id: str,
                                        model_hash: str, head_doctor_sig_hash: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_model = to_bytes32(model_hash)
        b32_sig = to_bytes32(head_doctor_sig_hash)
        sender = self.deployer_account or "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51"

        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.submitVerifiedModelUpdate(
                    round_num, hospital_id, doctor_id, head_doctor_id, b32_model, b32_sig
                )
                tx_hash = tx_call.transact({'from': sender, 'gas': 2000000})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                block_hex = "0x" + receipt.blockHash.hex().replace("0x", "")

                update_entry = {
                    "round": round_num,
                    "hospital_id": hospital_id,
                    "doctor_id": doctor_id,
                    "head_doctor_id": head_doctor_id,
                    "model_hash": model_hash,
                    "head_doctor_sig_hash": head_doctor_sig_hash,
                    "tx_hash": tx_hex,
                    "block_number": receipt.blockNumber,
                    "is_head_doctor_approved": True,
                    "on_chain": True
                }
                if round_num not in self.fl_round_updates:
                    self.fl_round_updates[round_num] = []
                self.fl_round_updates[round_num].append(update_entry)

                tx_obj = Transaction(
                    tx_type="VERIFIED_MODEL_UPDATE",
                    sender=f"{hospital_id}:{doctor_id}",
                    payload={"round": round_num, "model_hash": model_hash, "head_doctor_sig": head_doctor_sig_hash, "on_chain": True},
                    tx_hash=tx_hex
                )
                self.pending_transactions.append(tx_obj)
                self.mine_pending()

                return {
                    "tx_hash": tx_hex,
                    "block_number": receipt.blockNumber,
                    "block_hash": block_hex,
                    "on_chain": True
                }
            except Exception as e:
                print(f"[Blockchain Error] Live submitVerifiedModelUpdate note: {e}")

        # Fallback
        tx = Transaction(
            tx_type="VERIFIED_MODEL_UPDATE",
            sender=f"{hospital_id}:{doctor_id}",
            payload={"round": round_num, "model_hash": model_hash, "head_doctor_sig": head_doctor_sig_hash}
        )
        self.pending_transactions.append(tx)
        mined_block = self.mine_pending()

        update_entry = {
            "round": round_num,
            "hospital_id": hospital_id,
            "doctor_id": doctor_id,
            "head_doctor_id": head_doctor_id,
            "model_hash": model_hash,
            "head_doctor_sig_hash": head_doctor_sig_hash,
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index,
            "is_head_doctor_approved": True,
            "on_chain": False
        }
        if round_num not in self.fl_round_updates:
            self.fl_round_updates[round_num] = []
        self.fl_round_updates[round_num].append(update_entry)

        return {
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index,
            "block_hash": mined_block.hash,
            "on_chain": False
        }

    def submit_fl_model_update(self, round_num: int, model_hash: str, hospital_name: str) -> Dict[str, Any]:
        hid = "HOSP-METRO-01"
        if "Apollo" in hospital_name: hid = "HOSP-APOLLO-02"
        elif "Aster" in hospital_name: hid = "HOSP-ASTER-03"
        elif "City" in hospital_name: hid = "HOSP-CITY-04"
        doc_id = "DOC-METRO-01"
        head_id = "DOC-METRO-HEAD"
        head_sig = "0x" + hashlib.sha256(f"SIG:{hid}:{model_hash}".encode()).hexdigest()
        return self.submit_verified_fl_model_update(round_num, hid, doc_id, head_id, model_hash, head_sig)

    def verify_hospital_and_doctor_model_on_chain(self, hospital_id: str, doctor_id: str,
                                                  head_doctor_id: str, model_hash: str) -> Dict[str, Any]:
        """
        Triple-check verification gate executed by Central Server before admitting an update into FedAvg.
        """
        is_live = self.check_live_ganache()
        b32_model = to_bytes32(model_hash)

        if is_live and self.contract:
            try:
                is_h_val, is_d_val, is_head_val, is_mod_val = self.contract.functions.verifyHospitalAndDoctorModel(
                    hospital_id, doctor_id, head_doctor_id, b32_model
                ).call()
                return {
                    "is_hospital_verified": is_h_val,
                    "is_doctor_verified": is_d_val,
                    "is_head_doctor_approved": is_head_val,
                    "is_model_hash_committed": is_mod_val,
                    "is_fully_authentic": (is_h_val and is_d_val and is_head_val),
                    "verification_mode": "Ethereum Smart Contract (Live EVM)",
                    "contract_address": self.contract_address
                }
            except Exception as e:
                print(f"[Blockchain Error] verifyHospitalAndDoctorModel on-chain note: {e}")

        # Fallback check
        h_val = hospital_id in self.registered_hospitals
        d_val = doctor_id in self.registered_doctors
        head_val = head_doctor_id in self.registered_doctors and self.registered_doctors[head_doctor_id].get("is_head_doctor", False)
        
        # Check model updates cache
        mod_val = False
        for r_updates in self.fl_round_updates.values():
            for u in r_updates:
                if u.get("model_hash") == model_hash:
                    mod_val = True
                    break

        return {
            "is_hospital_verified": h_val,
            "is_doctor_verified": d_val,
            "is_head_doctor_approved": head_val,
            "is_model_hash_committed": mod_val,
            "is_fully_authentic": (h_val and d_val and head_val),
            "verification_mode": "Local Resilient Verification Engine",
            "contract_address": self.contract_address
        }

    def publish_global_fl_model(self, round_num: int, global_hash: str) -> Dict[str, Any]:
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(global_hash)
        sender = self.deployer_account or "0xB52f7303852B523e4992DE6ED81Cd85Fb875Ff51"

        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.publishGlobalModel(round_num, b32_hash)
                tx_hash = tx_call.transact({'from': sender, 'gas': 1000000})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                block_hex = "0x" + receipt.blockHash.hex().replace("0x", "")

                self.global_models[round_num] = global_hash

                tx_obj = Transaction(
                    tx_type="PUBLISH_GLOBAL_MODEL",
                    sender="FL-Coordinator",
                    payload={"round": round_num, "global_model_hash": global_hash, "on_chain": True},
                    tx_hash=tx_hex
                )
                self.pending_transactions.append(tx_obj)
                self.mine_pending()

                return {
                    "tx_hash": tx_hex,
                    "block_number": receipt.blockNumber,
                    "block_hash": block_hex,
                    "on_chain": True
                }
            except Exception as e:
                print(f"[Blockchain Error] Live publishGlobalModel failed ({e}), using fallback.")

        tx = Transaction(
            tx_type="PUBLISH_GLOBAL_MODEL",
            sender="FL-Coordinator",
            payload={"round": round_num, "global_model_hash": global_hash}
        )
        self.pending_transactions.append(tx)
        mined_block = self.mine_pending()
        self.global_models[round_num] = global_hash

        return {
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index,
            "block_hash": mined_block.hash,
            "on_chain": False
        }

    def submit_fl_model_update(self, round_num: int, model_hash: str, hospital_name: str) -> Dict[str, Any]:
        hid = "HOSP-METRO-01"
        if "Apollo" in hospital_name: hid = "HOSP-APOLLO-02"
        elif "Aster" in hospital_name: hid = "HOSP-ASTER-03"
        elif "City" in hospital_name: hid = "HOSP-CITY-04"
        doc_id = "DOC-METRO-01"
        head_id = "DOC-METRO-HEAD"
        head_sig = "0x" + hashlib.sha256(f"SIG:{hid}:{model_hash}".encode()).hexdigest()
        return self.submit_verified_fl_model_update(round_num, hid, doc_id, head_id, model_hash, head_sig)

    def get_blocks(self) -> List[Dict[str, Any]]:
        if self.check_live_ganache() and self.w3:
            try:
                latest_num = self.w3.eth.block_number
                blocks = []
                for b_num in range(latest_num, -1, -1):
                    raw_block = self.w3.eth.get_block(b_num, full_transactions=True)
                    txs = []
                    for tx in raw_block.transactions:
                        tx_hash = "0x" + (tx.hash.hex() if hasattr(tx.hash, "hex") else str(tx.hash)).replace("0x", "")
                        action = "ETHEREUM_TX"
                        sender = getattr(tx, "from", getattr(tx, "sender", "0x0"))
                        payload = {"value_wei": getattr(tx, "value", 0), "gas": getattr(tx, "gas", 0)}
                        for t in self.pending_transactions + [tx for b in self.chain for tx in b.transactions]:
                            if t.tx_hash.lower() == tx_hash.lower():
                                action = t.tx_type
                                payload = t.payload
                                break

                        txs.append({
                            "tx_hash": tx_hash,
                            "tx_type": action,
                            "sender": sender,
                            "payload": payload,
                            "timestamp": datetime_from_timestamp(raw_block.timestamp)
                        })

                    b_hash = "0x" + (raw_block.hash.hex() if hasattr(raw_block.hash, "hex") else str(raw_block.hash)).replace("0x", "")
                    p_hash = "0x" + (raw_block.parentHash.hex() if hasattr(raw_block.parentHash, "hex") else str(raw_block.parentHash)).replace("0x", "")

                    blocks.append({
                        "block_number": b_num,
                        "previous_hash": p_hash,
                        "block_hash": b_hash,
                        "validator": f"Ganache-Miner (Block #{b_num})",
                        "transactions_count": len(txs),
                        "transactions": txs,
                        "timestamp": datetime_from_timestamp(raw_block.timestamp)
                    })
                if blocks:
                    return blocks
            except Exception as e:
                print(f"[Blockchain Note] Live block extraction notice ({e}), displaying resilient ledger.")

        return [b.to_dict() for b in reversed(self.chain)]

# Singleton Instance
blockchain_ledger = BlockchainLedger()
