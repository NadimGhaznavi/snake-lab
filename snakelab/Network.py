"""Shared listener resolution, loaded once per process."""

from functools import lru_cache
from pathlib import Path

from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.NetworkConfiguration import NetworkConfiguration


class Network:
    @staticmethod
    @lru_cache(maxsize=1)
    def configuration() -> NetworkConfiguration:
        return NetworkConfiguration(Path(DSnakeLab.NETWORK_CONFIG_FILE))

    @staticmethod
    def binding(use: str) -> tuple[str, int]:
        return Network.configuration().binding(use)

    @staticmethod
    def destination(use: str) -> tuple[str, int]:
        return Network.configuration().destination(use)
