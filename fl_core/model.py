"""
Federated Learning Disease Risk Prediction Model
Implements a Multi-Layer Perceptron architecture with Differential Privacy Noise Injection
as described in the EPP-BCFL scientific paper:
theta^{t+1}_i = theta^t_i - eta * grad(L_i) + xi, where xi ~ N(0, sigma^2)

Supports both PyTorch (when installed) and a pure-Python neural network fallback
to guarantee zero crash on any review/demonstration machine.
"""

import math
import random
import hashlib
from typing import List, Dict, Any, Tuple

# Try importing torch; if not present, use pure-Python neural net engine
try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

if HAS_TORCH:
    class DiseasePredictionNN(nn.Module):
        def __init__(self, input_dim: int = 13, hidden_dim: int = 32, output_dim: int = 2):
            super(DiseasePredictionNN, self).__init__()
            self.network = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim, 16),
                nn.ReLU(),
                nn.Linear(16, output_dim)
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.network(x)

        def predict_risk(self, x: torch.Tensor) -> float:
            self.eval()
            with torch.no_grad():
                logits = self.forward(x)
                probabilities = torch.softmax(logits, dim=1)
                return probabilities[0][1].item()

else:
    # Pure Python Neural Model for zero-dependency execution
    class DiseasePredictionNN:
        def __init__(self, input_dim: int = 13, hidden_dim: int = 16, output_dim: int = 2):
            self.input_dim = input_dim
            self.hidden_dim = hidden_dim
            self.output_dim = output_dim
            # He / Xavier initialization
            scale1 = math.sqrt(2.0 / input_dim)
            self.w1 = [[random.gauss(0, scale1) for _ in range(hidden_dim)] for _ in range(input_dim)]
            self.b1 = [0.0] * hidden_dim
            scale2 = math.sqrt(2.0 / hidden_dim)
            self.w2 = [[random.gauss(0, scale2) for _ in range(output_dim)] for _ in range(hidden_dim)]
            self.b2 = [0.0] * output_dim

        def forward_single(self, x: List[float]) -> List[float]:
            # Hidden layer with ReLU
            h = [0.0] * self.hidden_dim
            for j in range(self.hidden_dim):
                val = sum(x[i] * self.w1[i][j] for i in range(self.input_dim)) + self.b1[j]
                h[j] = max(0.0, val)
            # Output layer with Softmax
            out = [0.0] * self.output_dim
            for k in range(self.output_dim):
                out[k] = sum(h[j] * self.w2[j][k] for j in range(self.hidden_dim)) + self.b2[k]
            # Softmax
            max_val = max(out)
            exp_out = [math.exp(v - max_val) for v in out]
            sum_exp = sum(exp_out)
            return [v / sum_exp for v in exp_out]

        def predict_risk(self, x: List[float]) -> float:
            probs = self.forward_single(x)
            return round(probs[1], 4)

        def get_flat_weights(self) -> List[float]:
            flat = []
            for row in self.w1: flat.extend(row)
            flat.extend(self.b1)
            for row in self.w2: flat.extend(row)
            flat.extend(self.b2)
            return flat

        def set_flat_weights(self, weights: List[float]) -> None:
            idx = 0
            for i in range(self.input_dim):
                for j in range(self.hidden_dim):
                    self.w1[i][j] = weights[idx]; idx += 1
            for j in range(self.hidden_dim):
                self.b1[j] = weights[idx]; idx += 1
            for j in range(self.hidden_dim):
                for k in range(self.output_dim):
                    self.w2[j][k] = weights[idx]; idx += 1
            for k in range(self.output_dim):
                self.b2[k] = weights[idx]; idx += 1

def apply_differential_privacy(weights: List[float], epsilon: float = 1.0, delta: float = 1e-5, sensitivity: float = 0.05) -> List[float]:
    """
    Gaussian Differential Privacy Perturbation Engine
    sigma = sqrt(2 * ln(1.25 / delta)) * (sensitivity / epsilon)
    xi ~ Normal(0, sigma^2)
    """
    if epsilon <= 0:
        return weights
    sigma = math.sqrt(2.0 * math.log(1.25 / delta)) * (sensitivity / epsilon)
    return [w + random.gauss(0, sigma) for w in weights]

def compute_model_hash(weights: List[float]) -> str:
    """Computes SHA-256 hash of model parameters for blockchain ledger"""
    hasher = hashlib.sha256()
    for w in weights:
        hasher.update(str(round(w, 6)).encode())
    return "0x" + hasher.hexdigest()
