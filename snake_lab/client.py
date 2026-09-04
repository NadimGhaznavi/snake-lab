"""Text-based administrative client for SnakeLab."""

import json
import uuid
from pathlib import Path
from typing import Any

import zmq

from constants.DSnakeLab import DSnakeLab
from snake_lab.protocol import (
    METHOD_HEALTH,
    METHOD_SIMULATION_STATUS,
    METHOD_SIMULATION_SUBMIT,
    PROTOCOL_VERSION,
)


class LabClient:
    """Synchronous request client for SnakeLab administrative operations."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DSnakeLab.PORT,
        timeout_ms: int = 3000,
    ) -> None:
        self.endpoint = f"tcp://{host}:{port}"
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.REQ)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self._socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self._socket.connect(self.endpoint)

    def request(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._socket.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request_id,
                "method": method,
                "payload": payload,
            }
        )
        response = self._socket.recv_json()

        if not isinstance(response, dict):
            raise TypeError("SnakeLab response must be a JSON object")
        if response.get("protocol_version") != PROTOCOL_VERSION:
            raise ValueError("SnakeLab response has an unsupported protocol")
        if response.get("request_id") != request_id:
            raise ValueError("SnakeLab response request_id does not match")
        return response

    def health(self) -> dict[str, Any]:
        return self.request(METHOD_HEALTH, {})

    def submit(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_SUBMIT, {"config": config})

    def status(self, run_id: str) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_STATUS, {"run_id": run_id})

    def close(self) -> None:
        self._socket.close()
        self._context.term()

    def menu(self) -> None:
        while True:
            print("\nSnakeLab Client")
            print("1. Health check")
            print("2. Submit simulation config")
            print("3. Simulation status")
            print("4. Quit")

            choice = input("Select an option: ").strip()
            if choice == "1":
                print(json.dumps(self.health(), separators=(",", ":")))
            elif choice == "2":
                config_path = Path(input("Config JSON file: ").strip())
                with config_path.open(encoding="utf-8") as config_file:
                    config = json.load(config_file)
                if not isinstance(config, dict):
                    raise TypeError("Simulation config must be a JSON object")
                print(json.dumps(self.submit(config), separators=(",", ":")))
            elif choice == "3":
                run_id = input("Run ID: ").strip()
                print(json.dumps(self.status(run_id), separators=(",", ":")))
            elif choice == "4":
                return
            else:
                print("Invalid option. Please select 1, 2, 3, or 4.")


def main() -> None:
    client = LabClient()
    try:
        client.menu()
    finally:
        client.close()


if __name__ == "__main__":
    main()
