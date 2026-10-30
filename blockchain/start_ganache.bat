@echo off
title SecureHealth Chain - Local Ethereum Blockchain Node (Ganache)
echo ======================================================================
echo  [*] SECUREHEALTH CHAIN: LOCAL ETHEREUM BLOCKCHAIN NODE (GANACHE)
echo ======================================================================
echo  RPC Endpoint:  http://127.0.0.1:7545
echo  Network ID:    5777
echo  Smart Contract: SecureHealthRegistry.sol
echo ======================================================================
ganache --port 7545 --wallet.mnemonic "securehealth blockchain federated learning ehr tamper proof demo network 2026" --wallet.totalAccounts 10 --chain.networkId 5777
pause
