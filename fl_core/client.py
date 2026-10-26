"""
Hospital Edge Client (Federated Learning Client with Flower & Differential Privacy)
Simulates a hospital edge node that trains locally on private EHR records
without exposing raw data to any central server.
"""

import flwr as fl
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from typing import List, Tuple, Dict
from model import DiseasePredictionNN, apply_differential_privacy, compute_model_hash

class HospitalFLClient(fl.client.NumPyClient):
    def __init__(self, hospital_id: str, train_data: Tuple[torch.Tensor, torch.Tensor], epsilon: float = 1.0):
        self.hospital_id = hospital_id
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = DiseasePredictionNN(input_dim=13, hidden_dim=32, output_dim=2).to(self.device)
        self.x_train, self.y_train = train_data
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.005)
        self.epsilon = epsilon # Differential Privacy budget

    def get_parameters(self, config: Dict[str, str]) -> List[np.ndarray]:
        """Returns local model parameters as numpy arrays"""
        return [val.cpu().numpy() for _, val in self.model.state_dict().items()]

    def set_parameters(self, parameters: List[np.ndarray]) -> None:
        """Sets global model parameters into local model"""
        params_dict = zip(self.model.state_dict().keys(), parameters)
        state_dict = {k: torch.tensor(v) for k, v in params_dict}
        self.model.load_state_dict(state_dict, strict=True)

    def fit(self, parameters: List[np.ndarray], config: Dict[str, str]) -> Tuple[List[np.ndarray], int, Dict]:
        """
        Trains model locally for 5 epochs on private hospital EHR data,
        adds Differential Privacy Gaussian noise, and returns perturbed weights.
        """
        self.set_parameters(parameters)
        self.model.train()

        # Local training loop (5 epochs)
        epochs = int(config.get("local_epochs", 5))
        for epoch in range(epochs):
            self.optimizer.zero_grad()
            outputs = self.model(self.x_train.to(self.device))
            loss = self.criterion(outputs, self.y_train.to(self.device))
            loss.backward()
            self.optimizer.step()

        # Convert state_dict tensors to list
        local_tensors = [val.cpu().clone() for _, val in self.model.state_dict().items()]
        
        # Apply Differential Privacy Gaussian Noise: xi ~ N(0, sigma^2)
        dp_perturbed_tensors = apply_differential_privacy(local_tensors, epsilon=self.epsilon)

        # Compute cryptographic hash for blockchain registration
        update_hash = compute_model_hash(dp_perturbed_tensors)
        print(f"[{self.hospital_id}] Training complete. Update Hash: {update_hash}")

        updated_params = [p.numpy() for p in dp_perturbed_tensors]
        num_samples = len(self.x_train)

        return updated_params, num_samples, {"update_hash": update_hash, "hospital_id": self.hospital_id}

    def evaluate(self, parameters: List[np.ndarray], config: Dict[str, str]) -> Tuple[float, int, Dict]:
        """Evaluates model performance on local validation data"""
        self.set_parameters(parameters)
        self.model.eval()

        with torch.no_grad():
            outputs = self.model(self.x_train.to(self.device))
            loss = self.criterion(outputs, self.y_train.to(self.device)).item()
            predictions = torch.argmax(outputs, dim=1)
            accuracy = (predictions == self.y_train.to(self.device)).float().mean().item()

        return float(loss), len(self.x_train), {"accuracy": accuracy}

if __name__ == "__main__":
    import sys
    node_id = sys.argv[1] if len(sys.argv) > 1 else "Hospital-Node-1"
    
    # Generate mock clinical data for demo testing (300 samples, 13 clinical vitals)
    np.random.seed(42)
    mock_x = torch.randn(300, 13)
    mock_y = torch.randint(0, 2, (300,))

    client = HospitalFLClient(hospital_id=node_id, train_data=(mock_x, mock_y), epsilon=1.0)
    print(f"[*] Starting Flower Federated Learning Client for: {node_id}")
    fl.client.start_numpy_client(server_address="127.0.0.1:8080", client=client)
