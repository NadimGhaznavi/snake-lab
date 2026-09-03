"""SnakeLab simulation runtime."""

from typing import Any

import torch


def runtime_description(torch_module: Any = torch) -> str:
    """Exercise PyTorch and describe the device used by the operation."""
    if torch_module.cuda.is_available():
        device = torch_module.device("cuda")
        location = f"GPU ({torch_module.cuda.get_device_name(device)})"
    else:
        device = torch_module.device("cpu")
        location = "CPU"

    probe = torch_module.ones(1, device=device)
    (probe + 1).sum().item()
    if device.type == "cuda":
        torch_module.cuda.synchronize(device)

    return f"Simulation running on {location}"


def run_simulation() -> None:
    """Run the initial simulator stack-validation workload."""
    print(runtime_description(), flush=True)
