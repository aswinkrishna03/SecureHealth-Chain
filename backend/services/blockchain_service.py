import os
import json
from web3 import Web3
from typing import Tuple, Dict, Any, Optional

GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:7545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
DEFAULT_ACCOUNT = os.getenv("DEFAULT_ACCOUNT", "")

class BlockchainService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
        self.contract = None
        self.simulated_records = {}
        self.is_connected = self.w3.is_connected()
        
        # Load ABI if contract address is configured
        if self.is_connected and CONTRACT_ADDRESS:
            try:
                with open("blockchain/build/SecureHealthRegistry.json", "r") as f:
                    contract_json = json.load(f)
                    abi = contract_json.get("abi", [])
                    self.contract = self.w3.eth.contract(address=CONTRACT_ADDRESS, abi=abi)
            except Exception as e:
                print(f"[BlockchainService Warning] Contract ABI not loaded: {e}")

    def register_ehr(self, record_uuid: str, record_hash_hex: str) -> Dict[str, Any]:
        """
        Stores an EHR SHA-256 hash onto the Ethereum blockchain.
        """
        # Ensure 32-byte hex format for Solidity bytes32
        record_hash_bytes = bytes.fromhex(record_hash_hex.replace("0x", ""))
        
        if self.is_connected and self.contract:
            try:
                account = DEFAULT_ACCOUNT or self.w3.eth.accounts[0]
                tx_hash = self.contract.functions.registerEHR(record_uuid, record_hash_bytes).transact({'from': account})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                return {
                    "success": True,
                    "tx_hash": tx_hash.hex(),
                    "block_number": receipt.blockNumber,
                    "mode": "live_blockchain"
                }
            except Exception as e:
                print(f"[Blockchain Error] Live transaction failed: {e}")
        
        # Fallback simulation mode for testing when Ganache is offline
        import hashlib
        simulated_tx = "0x" + hashlib.sha256((record_uuid + record_hash_hex).encode()).hexdigest()
        self.simulated_records[record_uuid] = {
            "record_hash": record_hash_hex,
            "tx_hash": simulated_tx,
            "timestamp": int(__import__("time").time()),
        }
        return {
            "success": True,
            "tx_hash": simulated_tx,
            "block_number": 1042,
            "mode": "simulated_ledger",
            "stored_hash": record_hash_hex,
        }

    def verify_ehr(self, record_uuid: str, incoming_hash_hex: str) -> Tuple[bool, str, Optional[int]]:
        """
        Verifies whether the current record's hash matches the tamper-evident on-chain hash.
        """
        incoming_hash_bytes = bytes.fromhex(incoming_hash_hex.replace("0x", ""))
        
        if self.is_connected and self.contract:
            try:
                is_valid, timestamp, recorded_by = self.contract.functions.verifyEHR(record_uuid, incoming_hash_bytes).call()
                return is_valid, recorded_by, timestamp
            except Exception as e:
                print(f"[Blockchain Verification Error] {e}")
                return False, "", None
        
        # Simulation must still compare against a value that was previously sealed.
        entry = self.simulated_records.get(record_uuid)
        if not entry:
            return False, "", None
        return (
            entry["record_hash"] == incoming_hash_hex,
            "SIMULATED_LEDGER",
            entry["timestamp"],
        )

blockchain_service = BlockchainService()
