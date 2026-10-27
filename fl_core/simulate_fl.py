"""Compatibility entry point for the measured local FL demonstration."""

try:
    from simulation import run_federated_training
except ImportError:
    from .simulation import run_federated_training


if __name__ == "__main__":
    import json
    print(json.dumps(run_federated_training(rounds=3, epsilon=1.0), indent=2))
