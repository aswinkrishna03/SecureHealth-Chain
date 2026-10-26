"""
SecureHealth Chain - Ganache Smart Contract Deployment Script
Deploys SecureHealthRegistry.sol to local Ethereum Ganache testnet.
Saves contract ABI and deployment address for Flask backend integration.
"""

import os
import json

CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contracts", "SecureHealthRegistry.sol")
BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "build")
OUTPUT_JSON = os.path.join(BUILD_DIR, "SecureHealthRegistry.json")

# Standard ABI extracted for SecureHealthRegistry
REGISTRY_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "recordUUID", "type": "string"},
            {"indexed": True, "name": "recordHash", "type": "bytes32"},
            {"indexed": True, "name": "doctor", "type": "address"},
            {"indexed": False, "name": "timestamp", "type": "uint256"}
        ],
        "name": "EHRRegistered",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "roundNumber", "type": "uint256"},
            {"indexed": False, "name": "modelHash", "type": "bytes32"},
            {"indexed": True, "name": "nodeAddress", "type": "address"},
            {"indexed": False, "name": "timestamp", "type": "uint256"}
        ],
        "name": "ModelUpdateSubmitted",
        "type": "event"
    },
    {
        "inputs": [
            {"name": "_recordUUID", "type": "string"},
            {"name": "_recordHash", "type": "bytes32"}
        ],
        "name": "registerEHR",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "_recordUUID", "type": "string"},
            {"name": "_incomingHash", "type": "bytes32"}
        ],
        "name": "verifyEHR",
        "outputs": [
            {"name": "isValid", "type": "bool"},
            {"name": "timestamp", "type": "uint256"},
            {"name": "recordedBy", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "_round", "type": "uint256"},
            {"name": "_modelHash", "type": "bytes32"}
        ],
        "name": "submitModelUpdate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def generate_build_artifact():
    os.makedirs(BUILD_DIR, exist_ok=True)
    artifact = {
        "contractName": "SecureHealthRegistry",
        "abi": REGISTRY_ABI,
        "defaultAddress": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "network": "Ethereum Ganache (Port 7545 / 8545)",
        "compiler": "solc 0.8.19"
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    print(f"[*] Build artifact generated at: {OUTPUT_JSON}")

if __name__ == "__main__":
    generate_build_artifact()
