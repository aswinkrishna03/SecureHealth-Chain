"""
SecureHealth Chain - Deploy Smart Contract to Ganache Testnet
Deploys SecureHealthRegistry.sol to http://127.0.0.1:7545
"""
import os
import json
import sys

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

    tx_hash = ContractFactory.constructor().transact({"from": deployer, "gas": 3000000})
    print(f" [*] Deployment Tx Hash:   {tx_hash.hex()}")

    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print(f" [SUCCESS] Contract Deployed At Address: {contract_address}")
    print(f" [*] Mined in Block:       #{tx_receipt.blockNumber}")
    print(f" [*] Gas Used:             {tx_receipt.gasUsed}")

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
    print(" [READY] Fully functional smart contract is live on Ethereum blockchain!")
    print("=" * 70)
    return contract_address

if __name__ == "__main__":
    deploy()
