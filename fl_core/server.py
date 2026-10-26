"""
Central Federated Learning Aggregator Server
Coordinates multi-hospital rounds, runs Federated Averaging (FedAvg),
and records aggregated model hashes for blockchain publication.
"""

import flwr as fl
from typing import List, Tuple, Dict, Optional
import numpy as np
import hashlib
from flwr.common import Parameters, Scalar

class BlockchainFedAvg(fl.server.strategy.FedAvg):
    def aggregate_fit(
        self,
        server_round: int,
        results: List[Tuple[fl.server.client_proxy.ClientProxy, fl.common.FitRes]],
        failures: List[Tuple[fl.server.client_proxy.ClientProxy, fl.common.FitRes]]
    ) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
        """
        Aggregates weights from hospital nodes and hashes the global model update.
        """
        aggregated_parameters, metrics = super().aggregate_fit(server_round, results, failures)

        if aggregated_parameters is not None:
            # Convert parameters to bytes to compute global model hash
            hasher = hashlib.sha256()
            for tensor_bytes in aggregated_parameters.tensors:
                hasher.update(tensor_bytes)
            global_model_hash = "0x" + hasher.hexdigest()
            
            print(f"\n==========================================")
            print(f" [ROUND {server_round}] Aggregation Complete!")
            print(f" Global Model Hash: {global_model_hash}")
            print(f" Participating Nodes: {len(results)}")
            print(f"==========================================\n")
            
            # Record hash into metrics dictionary
            metrics["global_model_hash"] = global_model_hash
            metrics["participating_nodes"] = len(results)

        return aggregated_parameters, metrics

def start_fl_server(rounds: int = 5, port: int = 8080):
    strategy = BlockchainFedAvg(
        fraction_fit=1.0,
        min_fit_clients=2,
        min_available_clients=2,
        initial_parameters=None
    )

    print(f"[*] Starting Flower Central FL Server on port {port}...")
    fl.server.start_server(
        server_address=f"0.0.0.0:{port}",
        config=fl.server.ServerConfig(num_rounds=rounds),
        strategy=strategy,
    )

if __name__ == "__main__":
    start_fl_server(rounds=3, port=8080)
