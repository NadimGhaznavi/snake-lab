"""Resolve listener defaults and validate external production overrides."""

import argparse
import ipaddress
import json
from pathlib import Path

from snakelab.constants.DSnakeLab import DSnakeLab


class NetworkConfiguration:
    """A process snapshot of the configured IPv4 listeners."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.bindings = {
            use: (interface, port)
            for use, interface, port in DSnakeLab.CMDB_NETWORK
        }
        try:
            with path.open(encoding="utf-8") as source:
                data = json.load(source)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            raise ValueError(f"{path}: {error}") from error
        if not isinstance(data, dict) or set(data) - {"network"}:
            self._invalid("expected an object containing only 'network'")
        network = data.get("network", {})
        if not isinstance(network, dict):
            self._invalid("network must be an object")
        for use, fields in network.items():
            if use not in self.bindings:
                self._invalid(f"unknown network use: {use}")
            if not isinstance(fields, dict) or set(fields) - {"interface", "port"}:
                self._invalid(f"network.{use}: expected only interface and port fields")
            interface, port = self.bindings[use]
            if "interface" in fields:
                interface = fields["interface"]
                try:
                    if not isinstance(interface, str):
                        raise ValueError("expected an IPv4 string")
                    ipaddress.IPv4Address(interface)
                except ValueError:
                    self._invalid(f"network.{use}.interface: expected an IPv4 address")
            if "port" in fields:
                port = fields["port"]
                if type(port) is not int or not 1 <= port <= 65535:
                    self._invalid(f"network.{use}.port: expected an integer from 1 to 65535")
            self.bindings[use] = interface, port

    def _invalid(self, message: str) -> None:
        raise ValueError(f"{self.path}: {message}")

    def binding(self, use: str) -> tuple[str, int]:
        return self.bindings[use]

    def destination(self, use: str) -> tuple[str, int]:
        interface, port = self.binding(use)
        return ("127.0.0.1" if interface == "0.0.0.0" else interface), port

    @staticmethod
    def create(path: Path) -> None:
        """Create readable defaults without replacing an existing configuration."""
        data = {"network": {
            use: {"interface": interface, "port": port}
            for use, interface, port in DSnakeLab.CMDB_NETWORK
        }}
        try:
            with path.open("x", encoding="utf-8") as target:
                json.dump(data, target, indent=2)
                target.write("\n")
                path.chmod(0o644)
        except FileExistsError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path(DSnakeLab.NETWORK_CONFIG_FILE))
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    try:
        if args.create:
            NetworkConfiguration.create(args.path)
        config = NetworkConfiguration(args.path)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.show:
        for use in config.bindings:
            interface, port = config.destination(use)
            print(f"[INFO] {use}: tcp://{interface}:{port}")


if __name__ == "__main__":
    main()
