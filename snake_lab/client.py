"""Text-based administrative client for SnakeLab."""

import json
from typing import Any

import zmq

from constants.DSnakeLab import DSnakeLab


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

    def request(self, message: str) -> dict[str, Any]:
        """Send one request and return its JSON-object response."""
        self._socket.send_string(message)
        response = self._socket.recv_json()
        if not isinstance(response, dict):
            raise TypeError("SnakeLab response must be a JSON object")
        return response

    def health(self) -> dict[str, Any]:
        """Return the server health response."""
        return self.request("health")

    def close(self) -> None:
        """Release the ZeroMQ socket and context."""
        self._socket.close()
        self._context.term()

    def menu(self) -> None:
        """Run the administrative menu until the user quits."""
        while True:
            print("\nSnakeLab Client")
            print("1. Health check")
            print("2. Quit")

            choice = input("Select an option: ").strip()
            if choice == "1":
                print(json.dumps(self.health(), separators=(",", ":")))
            elif choice == "2":
                return
            else:
                print("Invalid option. Please select 1 or 2.")


def main() -> None:
    """Run the SnakeLab administrative client."""
    client = LabClient()
    try:
        client.menu()
    finally:
        client.close()


if __name__ == "__main__":
    main()

