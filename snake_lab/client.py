"""Text-based administrative client for SnakeLab."""

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import zmq
import zmq.asyncio

from constants.DSnakeLab import DSnakeLab
from snake_lab.protocol import (
    METHOD_HEALTH,
    METHOD_SIMULATION_ACTIVE,
    METHOD_SIMULATION_CANCEL,
    METHOD_SIMULATION_PAUSE,
    METHOD_SIMULATION_RESUME,
    METHOD_SIMULATION_SET_MOVE_DELAY,
    METHOD_SIMULATION_STATUS,
    METHOD_SIMULATION_SUBMIT,
    PROTOCOL_VERSION,
)


def _request_message(
    request_id: str, method: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "method": method,
        "payload": payload,
    }


def _validate_response(
    response: Any, request_id: str
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise TypeError("SnakeLab response must be a JSON object")
    if response.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("SnakeLab response has an unsupported protocol")
    if response.get("request_id") != request_id:
        raise ValueError("SnakeLab response request_id does not match")
    return response


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
        self._socket.send_json(_request_message(request_id, method, payload))
        response = self._socket.recv_json()
        return _validate_response(response, request_id)

    def health(self) -> dict[str, Any]:
        return self.request(METHOD_HEALTH, {})

    def submit(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_SUBMIT, {"config": config})

    def status(self, run_id: str) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_STATUS, {"run_id": run_id})

    def active(self) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_ACTIVE, {})

    def pause(self, run_id: str) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_PAUSE, {"run_id": run_id})

    def resume(self, run_id: str) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_RESUME, {"run_id": run_id})

    def cancel(self, run_id: str) -> dict[str, Any]:
        return self.request(METHOD_SIMULATION_CANCEL, {"run_id": run_id})

    def set_move_delay(
        self, run_id: str, move_delay_ms: int
    ) -> dict[str, Any]:
        return self.request(
            METHOD_SIMULATION_SET_MOVE_DELAY,
            {"run_id": run_id, "move_delay_ms": move_delay_ms},
        )

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
                print(
                    json.dumps(
                        self.submit(_load_config(config_path)),
                        separators=(",", ":"),
                    )
                )
            elif choice == "3":
                run_id = input("Run ID: ").strip()
                print(json.dumps(self.status(run_id), separators=(",", ":")))
            elif choice == "4":
                return
            else:
                print("Invalid option. Please select 1, 2, 3, or 4.")


class AsyncLabClient:
    """Async request client used by Textual without blocking its event loop."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DSnakeLab.PORT,
        timeout_ms: int = 3000,
    ) -> None:
        self.endpoint = f"tcp://{host}:{port}"
        self._timeout = timeout_ms / 1000
        self._context = zmq.asyncio.Context()
        self._lock = asyncio.Lock()

    async def request(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._lock:
            socket = self._context.socket(zmq.REQ)
            socket.setsockopt(zmq.LINGER, 0)
            socket.connect(self.endpoint)
            request_id = str(uuid.uuid4())
            try:
                await asyncio.wait_for(
                    socket.send_json(
                        _request_message(request_id, method, payload)
                    ),
                    self._timeout,
                )
                response = await asyncio.wait_for(
                    socket.recv_json(), self._timeout
                )
            finally:
                socket.close()
            return _validate_response(response, request_id)

    async def active(self) -> dict[str, Any]:
        return await self.request(METHOD_SIMULATION_ACTIVE, {})

    async def pause(self, run_id: str) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_PAUSE, {"run_id": run_id}
        )

    async def resume(self, run_id: str) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_RESUME, {"run_id": run_id}
        )

    async def cancel(self, run_id: str) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_CANCEL, {"run_id": run_id}
        )

    async def set_move_delay(
        self, run_id: str, move_delay_ms: int
    ) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_SET_MOVE_DELAY,
            {"run_id": run_id, "move_delay_ms": move_delay_ms},
        )

    def close(self) -> None:
        self._context.term()


def _load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise TypeError("Simulation config must be a JSON object")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operate SnakeLab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DSnakeLab.PORT)
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="submit a JSON simulation config and exit",
    )
    args = parser.parse_args(argv)

    client = LabClient(host=args.host, port=args.port)
    try:
        if args.config is not None:
            response = client.submit(_load_config(args.config))
            print(json.dumps(response, separators=(",", ":")))
            return 0 if response.get("status") == "ok" else 1
        client.menu()
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
