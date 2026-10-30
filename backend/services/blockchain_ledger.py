"""Live Ethereum Blockchain Ledger & Smart Contract Service for SecureHealth Chain.

Integrates with a live Ganache local Ethereum testnet node and the deployed
SecureHealthRegistry.sol smart contract using web3.py.
Maintains in-memory fallback for resilient local development if Ganache is temporarily offline.
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
    # If not 64 hex chars, hash it to produce deterministic 32 bytes
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
            "block_hash": self.hash,
            "previous_hash": self.previous_hash,
            "validator": self.validator,
            "timestamp": datetime_from_timestamp(self.timestamp),
            "transactions_count": len(self.transactions),
            "transactions": [tx.to_dict() for tx in self.transactions]
        }

class BlockchainLedger:
    def __init__(self):
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.active_validators = ["Ganache-Validator-0", "Ganache-Validator-1", "Ganache-Validator-2"]
        
        # State registries matching SecureHealthRegistry.sol
        self.ehr_registry: Dict[str, Dict[str, Any]] = {}
        self.fl_round_updates: Dict[int, List[Dict[str, Any]]] = {}
        self.global_models: Dict[int, str] = {}

        # Web3 and Smart Contract configuration
        self.w3: Optional[Any] = None
        self.contract: Optional[Any] = None
        self.contract_address: str = "0x5f18C8CF1b857ec272B4357C0736b60E61324cd1"
        self.deployer_account: Optional[str] = None
        self.contract_abi: List[Dict[str, Any]] = []

        # Initialize Web3 & Contract
        self._init_web3()

        # Initialize Genesis Block for in-memory tracker
        self.create_genesis_block()

    def _init_web3(self):
        if not HAS_WEB3:
            print("[Blockchain] web3.py not installed; operating in local in-memory mode.")
            return

        try:
            self.w3 = Web3(Web3.HTTPProvider(GANACHE_RPC_URL, request_kwargs={"timeout": 5}))
            if self.w3.is_connected():
                print(f"[Blockchain] Connected to live Ethereum Ganache at {GANACHE_RPC_URL}")
                accounts = self.w3.eth.accounts
                if accounts:
                    self.deployer_account = accounts[0]

                # Load deployed contract metadata
                if os.path.exists(DEPLOYED_CONTRACT_PATH):
                    with open(DEPLOYED_CONTRACT_PATH, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        self.contract_address = meta.get("contractAddress", self.contract_address)
                        self.contract_abi = meta.get("abi", [])
                        if meta.get("deployer"):
                            self.deployer_account = meta["deployer"]

                if self.contract_abi and self.contract_address:
                    checksum_addr = self.w3.to_checksum_address(self.contract_address)
                    self.contract = self.w3.eth.contract(address=checksum_addr, abi=self.contract_abi)
                    print(f"[Blockchain] Smart Contract loaded at {checksum_addr} (Deployer: {self.deployer_account})")
            else:
                print(f"[Blockchain] Ganache not reachable at {GANACHE_RPC_URL}; using fallback ledger.")
        except Exception as e:
            print(f"[Blockchain Initialization Warning] {e}")

    def check_live_ganache(self) -> bool:
        """Checks if live Ganache testnet JSON-RPC is responsive."""
        if self.w3:
            try:
                return bool(self.w3.is_connected())
            except Exception:
                pass
        return False

    def create_genesis_block(self):
        genesis_tx = Transaction(
            tx_type="CONTRACT_DEPLOYMENT",
            sender="0x0000000000000000000000000000000000000000",
            payload={"contract": "SecureHealthRegistry.sol", "address": self.contract_address}
        )
        genesis_block = Block(
            index=0,
            previous_hash="0x0000000000000000000000000000000000000000000000000000000000000000",
            transactions=[genesis_tx],
            validator="Genesis"
        )
        self.chain.append(genesis_block)

    def mine_pending(self, validator: Optional[str] = None) -> Block:
        if not self.pending_transactions:
            return self.chain[-1]
        
        prev_block = self.chain[-1]
        val = validator or self.active_validators[len(self.chain) % len(self.active_validators)]
        new_block = Block(
            index=len(self.chain),
            previous_hash=prev_block.hash,
            transactions=list(self.pending_transactions),
            validator=val
        )
        self.chain.append(new_block)
        self.pending_transactions = []
        return new_block

    def register_ehr_record(self, record_uuid: str, record_hash: str, doctor_address: str = "0x9876543210FedCba9876543210FedCba98765432") -> Dict[str, Any]:
        """
        Registers an EHR SHA-256 fingerprint on the live Ethereum blockchain via SecureHealthRegistry.sol.
        Falls back to local ledger if Ganache is offline.
        """
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(record_hash)
        sender = self.deployer_account or doctor_address

        # 1. Attempt live Ethereum transaction
        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.registerEHR(record_uuid, b32_hash)
                tx_hash = tx_call.transact({'from': sender})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                block_hex = "0x" + receipt.blockHash.hex().replace("0x", "")

                # Record in local state cache
                self.ehr_registry[record_uuid] = {
                    "record_hash": record_hash,
                    "recorded_by": sender,
                    "block_number": receipt.blockNumber,
                    "tx_hash": tx_hex,
                    "timestamp": time.time(),
                    "on_chain": True
                }

                # Also log in in-memory block tracking
                tx_obj = Transaction(
                    tx_type="REGISTER_EHR",
                    sender=sender,
                    payload={"record_uuid": record_uuid, "record_hash": record_hash, "on_chain": True},
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

        # 2. Resilient local fallback
        tx = Transaction(
            tx_type="REGISTER_EHR",
            sender=doctor_address,
            payload={"record_uuid": record_uuid, "record_hash": record_hash}
        )
        self.pending_transactions.append(tx)
        mined_block = self.mine_pending()

        self.ehr_registry[record_uuid] = {
            "record_hash": record_hash,
            "recorded_by": doctor_address,
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
        """
        Verifies EHR record integrity against on-chain smart contract state.
        """
        is_live = self.check_live_ganache()
        b32_incoming = to_bytes32(incoming_hash)

        # 1. Attempt live smart contract verification
        if is_live and self.contract:
            try:
                is_valid, timestamp, recorded_by = self.contract.functions.verifyEHR(record_uuid, b32_incoming).call()
                # Fetch stored hash directly from smart contract storage
                stored_hash_bytes, on_chain_recorder, on_chain_ts = self.contract.functions.getEHR(record_uuid).call()
                stored_hash_hex = "0x" + stored_hash_bytes.hex()
                
                # Retrieve block / tx from cache or state
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
                        "timestamp": datetime_from_timestamp(timestamp if timestamp > 0 else time.time()),
                        "tamper_status": "AUTHENTIC" if is_valid else "TAMPER_DETECTED",
                        "verification_engine": "Ethereum Smart Contract (Ganache)"
                    }
            except Exception as e:
                print(f"[Blockchain Error] Live verifyEHR failed ({e}), using fallback verification.")

        # 2. Resilient local fallback
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
            "timestamp": datetime_from_timestamp(entry["timestamp"]),
            "tamper_status": "AUTHENTIC" if is_valid else "TAMPER_DETECTED",
            "verification_engine": "Local Ledger Engine"
        }

    def submit_fl_model_update(self, round_num: int, model_hash: str, node_id: str) -> Dict[str, Any]:
        """
        Submits a hospital edge model update hash to the Ethereum blockchain via submitModelUpdate(round, hash).
        """
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(model_hash)
        sender = self.deployer_account or "0x1234567890abcdef1234567890abcdef12345678"

        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.submitModelUpdate(round_num, b32_hash)
                tx_hash = tx_call.transact({'from': sender})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                tx_hex = "0x" + receipt.transactionHash.hex().replace("0x", "")
                block_hex = "0x" + receipt.blockHash.hex().replace("0x", "")

                if round_num not in self.fl_round_updates:
                    self.fl_round_updates[round_num] = []
                self.fl_round_updates[round_num].append({
                    "node": node_id,
                    "model_hash": model_hash,
                    "tx_hash": tx_hex,
                    "block_number": receipt.blockNumber
                })

                # In-memory mirror
                tx_obj = Transaction(
                    tx_type="MODEL_UPDATE",
                    sender=node_id,
                    payload={"round": round_num, "model_hash": model_hash, "on_chain": True},
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
                print(f"[Blockchain Error] Live submitModelUpdate failed ({e}), using fallback.")

        # Fallback
        tx = Transaction(
            tx_type="MODEL_UPDATE",
            sender=node_id,
            payload={"round": round_num, "model_hash": model_hash}
        )
        self.pending_transactions.append(tx)
        mined_block = self.mine_pending()

        if round_num not in self.fl_round_updates:
            self.fl_round_updates[round_num] = []
        self.fl_round_updates[round_num].append({
            "node": node_id,
            "model_hash": model_hash,
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index
        })

        return {
            "tx_hash": tx.tx_hash,
            "block_number": mined_block.index,
            "block_hash": mined_block.hash,
            "on_chain": False
        }

    def publish_global_fl_model(self, round_num: int, global_hash: str) -> Dict[str, Any]:
        """
        Publishes the aggregated global model hash to the Ethereum blockchain via publishGlobalModel(round, hash).
        """
        is_live = self.check_live_ganache()
        b32_hash = to_bytes32(global_hash)
        sender = self.deployer_account or "0x1234567890abcdef1234567890abcdef12345678"

        if is_live and self.contract and self.w3:
            try:
                tx_call = self.contract.functions.publishGlobalModel(round_num, b32_hash)
                tx_hash = tx_call.transact({'from': sender})
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

        # Fallback
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

    def get_blocks(self) -> List[Dict[str, Any]]:
        """
        Returns the blockchain block explorer view. If connected to live Ganache,
        fetches real mined Ethereum blocks and transactions from the node.
        """
        if self.check_live_ganache() and self.w3:
            try:
                latest_num = self.w3.eth.block_number
                start_num = max(0, latest_num - 25)
                live_blocks = []
                for b_idx in range(latest_num, start_num - 1, -1):
                    raw_block = self.w3.eth.get_block(b_idx, full_transactions=True)
                    tx_list = []
                    for tx in raw_block.transactions:
                        tx_hash = "0x" + (tx.hash.hex() if hasattr(tx.hash, "hex") else str(tx.hash)).replace("0x", "")
                        from_addr = tx.get("from", "")
                        to_addr = tx.get("to", self.contract_address)
                        tx_list.append({
                            "tx_hash": tx_hash,
                            "tx_type": "CONTRACT_EXECUTION" if to_addr else "CONTRACT_DEPLOYMENT",
                            "sender": from_addr,
                            "payload": {
                                "to": to_addr,
                                "gas": tx.get("gas", 0),
                                "gasPrice": tx.get("gasPrice", 0),
                                "value": tx.get("value", 0)
                            },
                            "timestamp": datetime_from_timestamp(raw_block.timestamp)
                        })
                    
                    b_hash = "0x" + (raw_block.hash.hex() if hasattr(raw_block.hash, "hex") else str(raw_block.hash)).replace("0x", "")
                    p_hash = "0x" + (raw_block.parentHash.hex() if hasattr(raw_block.parentHash, "hex") else str(raw_block.parentHash)).replace("0x", "")
                    
                    live_blocks.append({
                        "block_number": raw_block.number,
                        "block_hash": b_hash,
                        "previous_hash": p_hash,
                        "validator": raw_block.miner or "Ganache-Validator-PoA",
                        "timestamp": datetime_from_timestamp(raw_block.timestamp),
                        "transactions_count": len(tx_list),
                        "transactions": tx_list
                    })
                if live_blocks:
                    return live_blocks
            except Exception as e:
                print(f"[Blockchain Warning] Error reading live blocks ({e}); using internal chain.")

        # Fallback in-memory chain
        return [b.to_dict() for b in reversed(self.chain)]

# Singleton Instance
blockchain_ledger = BlockchainLedger()
