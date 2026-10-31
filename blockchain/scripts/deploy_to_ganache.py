"""
SecureHealth Chain - Deploy Smart Contract to Ganache Testnet
Deploys SecureHealthRegistry.sol to http://127.0.0.1:7545
Registers all participating Hospital Nodes and certified Doctor identities on-chain.
"""
import os
import json
import sys
import hashlib

def to_b32(val: str) -> bytes:
    clean = val.replace("0x", "").strip()
    if len(clean) == 64:
        try:
            return bytes.fromhex(clean)
        except ValueError:
            pass
    return hashlib.sha256(val.encode("utf-8")).digest()

def deploy():
    print("=" * 70)
    print(" [*] SECUREHEALTH CHAIN: SMART CONTRACT DEPLOYMENT")
    print("=" * 70)

    try:
        from web3 import Web3
    except ImportError:
        print("[!] web3.py is not installed yet. Run: pip install web3")
        return None

    rpc_url = os.environ.get("GANACHE_URL", "http://127.0.0.1:7545")
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        print(f"[!] Cannot connect to Ganache RPC at {rpc_url}")
        print("    Please start Ganache first: run 'blockchain\\start_ganache.bat'")
        return None

    print(f" [PASS] Connected to Ethereum Ganache at {rpc_url}")
    print(f" [*] Current Block Number: {w3.eth.block_number}")
    print(f" [*] Available Accounts:   {len(w3.eth.accounts)}")

    deployer = w3.eth.accounts[0]
    balance = w3.eth.get_balance(deployer)
    print(f" [*] Deployer Account:     {deployer} (Balance: {w3.from_wei(balance, 'ether')} ETH)")

    # Load ABI & Bytecode
    build_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build"))
    abi_files = [f for f in os.listdir(build_dir) if f.endswith(".abi")]
    bin_files = [f for f in os.listdir(build_dir) if f.endswith(".bin")]

    if not abi_files or not bin_files:
        print("[!] Compiled ABI or BIN not found in build directory.")
        return None

    with open(os.path.join(build_dir, abi_files[0]), "r", encoding="utf-8") as f:
        abi = json.load(f)

    with open(os.path.join(build_dir, bin_files[0]), "r", encoding="utf-8") as f:
        bytecode = f.read().strip()
        if not bytecode.startswith("0x"):
            bytecode = "0x" + bytecode

    print(" [*] Deploying SecureHealthRegistry.sol to Ethereum EVM...")
    ContractFactory = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx_hash = ContractFactory.constructor().transact({"from": deployer, "gas": 5000000})
    print(f" [*] Deployment Tx Hash:   {tx_hash.hex()}")

    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print(f" [SUCCESS] Contract Deployed At Address: {contract_address}")
    print(f" [*] Mined in Block:       #{tx_receipt.blockNumber}")
    print(f" [*] Gas Used:             {tx_receipt.gasUsed}")

    # Initialize Contract Instance
    contract = w3.eth.contract(address=contract_address, abi=abi)

    # 1. Register Multi-Hospital Nodes on Blockchain
    print(" [*] Minting Multi-Hospital Registrations on Ethereum...")
    hospitals = [
        ("HOSP-METRO-01", "Metro Health General Hospital", "0x0111111111111111111111111111111111111111111111111111111111111111"),
        ("HOSP-APOLLO-02", "Apollo Healthcare Network", "0x0222222222222222222222222222222222222222222222222222222222222222"),
        ("HOSP-ASTER-03", "Aster Medcity Silo", "0x0333333333333333333333333333333333333333333333333333333333333333"),
        ("HOSP-CITY-04", "City Central Clinic", "0x0444444444444444444444444444444444444444444444444444444444444444")
    ]
    for hid, hname, hhash in hospitals:
        tx = contract.functions.registerHospital(hid, hname, to_b32(hhash)).transact({"from": deployer, "gas": 500000})
        w3.eth.wait_for_transaction_receipt(tx)
        print(f"     -> Registered Hospital: {hname} ({hid}) on chain")

    # 2. Register Certified Doctors & Head Doctors on Blockchain
    print(" [*] Minting Doctor Cryptographic Credentials on Ethereum...")
    doctors = [
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
    for doc in doctors:
        tx = contract.functions.registerDoctor(
            doc[0], doc[1], doc[2], doc[3], doc[4], to_b32(doc[5]), doc[6]
        ).transact({"from": deployer, "gas": 500000})
        w3.eth.wait_for_transaction_receipt(tx)
        role_label = "Head Doctor (CMO)" if doc[6] else f"Doctor ({doc[3]})"
        print(f"     -> Registered {role_label}: {doc[2]} (License: {doc[4]}) on chain")

    # Save to deployed_contract.json
    output_path = os.path.join(build_dir, "deployed_contract.json")
    deployment_info = {
        "contractName": "SecureHealthRegistry",
        "contractAddress": contract_address,
        "transactionHash": tx_hash.hex(),
        "blockNumber": tx_receipt.blockNumber,
        "deployer": deployer,
        "rpcUrl": rpc_url,
        "abi": abi
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deployment_info, f, indent=2)
    print(f" [*] Deployment metadata saved: {output_path}")

    # Update .env
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    if os.path.exists(env_path):
        lines = []
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        has_contract = False
        has_rpc = False
        new_lines = []
        for line in lines:
            if line.startswith("BLOCKCHAIN_CONTRACT_ADDRESS="):
                new_lines.append(f"BLOCKCHAIN_CONTRACT_ADDRESS={contract_address}\n")
                has_contract = True
            elif line.startswith("GANACHE_URL="):
                new_lines.append(f"GANACHE_URL={rpc_url}\n")
                has_rpc = True
            else:
                new_lines.append(line)
        if not has_contract:
            new_lines.append(f"BLOCKCHAIN_CONTRACT_ADDRESS={contract_address}\n")
        if not has_rpc:
            new_lines.append(f"GANACHE_URL={rpc_url}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(" [*] Updated .env file with active contract address.")

    print("=" * 70)
    print(" [READY] Fully functional multi-hospital smart contract is live on Ethereum blockchain!")
    print("=" * 70)
    return contract_address

if __name__ == "__main__":
    deploy()
