"""SnakeLab simulation runtime."""

from copy import deepcopy
from typing import Any

import torch

from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DSnakeLab import DSnakeLab
from utils.MyLog import MyLog


class Simulator:
    """Execute one isolated SnakeLab simulation."""

    def __init__(
        self,
        config: dict[str, Any],
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        torch_module: Any = torch,
        log: MyLog | None = None,
    ) -> None:
        self.config = deepcopy(config)
        self._torch = torch_module
        self.log = log or MyLog(
            client_id=DModule.SIMULATOR,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=True,
        )
        if self._torch.cuda.is_available():
            self.device = self._torch.device("cuda")
            device_name = self._torch.cuda.get_device_name(self.device)
            self._location = f"GPU ({device_name})"
        else:
            self.device = self._torch.device("cpu")
            self._location = "CPU"

    @property
    def runtime_description(self) -> str:
        return f"Simulation running on {self._location}"

    def run(self) -> None:
        """Run the initial simulator stack-validation workload."""
        probe = self._torch.ones(1, device=self.device)
        (probe + 1).sum().item()
        if self.device.type == "cuda":
            self._torch.cuda.synchronize(self.device)

        self.log.info(self.runtime_description)
