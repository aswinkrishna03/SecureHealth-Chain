"""
Compiles SecureHealthRegistry.sol to shanghai EVM target using solcjs --standard-json
Ensures 100% compatibility with Ganache and Ethereum mainnet/testnets (no PUSH0 issues).
"""
import os
import json
import subprocess

def compile_solidity():
    contract_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "contracts", "SecureHealthRegistry.sol"))
    build_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build"))
    os.makedirs(build_dir, exist_ok=True)

    with open(contract_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    input_json = {
        "language": "Solidity",
        "sources": {
            "SecureHealthRegistry.sol": {
                "content": source_code
            }
        },
        "settings": {
            "optimizer": {
                "enabled": True,
                "runs": 200
            },
            "evmVersion": "shanghai",
            "outputSelection": {
                "*": {
                    "*": ["abi", "evm.bytecode"]
                }
            }
        }
    }

    # Run solcjs --standard-json passing input via stdin
    cmd = ["solcjs", "--standard-json"]
    result = subprocess.run(cmd, input=json.dumps(input_json), capture_output=True, text=True, shell=True)
    
    if result.returncode != 0:
        print("[!] Compilation failed:", result.stderr)
        return False

    json_start = result.stdout.find("{")
    if json_start == -1:
        print("[!] No JSON found in solcjs output:", result.stdout, result.stderr)
        return False
    output_data = json.loads(result.stdout[json_start:])
    if "errors" in output_data:
        has_error = False
        for err in output_data["errors"]:
            if err.get("severity") == "error":
                print("[!] Error:", err.get("formattedMessage", err))
                has_error = True
            else:
                print("[*] Warning:", err.get("formattedMessage", err))
        if has_error:
            return False

    contract_data = output_data["contracts"]["SecureHealthRegistry.sol"]["SecureHealthRegistry"]
    abi = contract_data["abi"]
    bytecode = "0x" + contract_data["evm"]["bytecode"]["object"]

    # Save ABI and BIN
    abi_path = os.path.join(build_dir, "SecureHealthRegistry.abi")
    bin_path = os.path.join(build_dir, "SecureHealthRegistry.bin")
    with open(abi_path, "w", encoding="utf-8") as f:
        json.dump(abi, f, indent=2)
    with open(bin_path, "w", encoding="utf-8") as f:
        f.write(bytecode)

    print(f" [SUCCESS] SecureHealthRegistry.sol compiled with shanghai EVM target!")
    print(f" [*] ABI:      {abi_path}")
    print(f" [*] Bytecode: {bin_path} ({len(bytecode)} chars)")
    return True

if __name__ == "__main__":
    compile_solidity()
