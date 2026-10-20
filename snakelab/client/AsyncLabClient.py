"""Async ZeroMQ client used by the Snake Lab Textual application."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import zmq
import zmq.asyncio

from snakelab.Network import Network
from snakelab.zmq.Protocol import (
    METHOD_SIMULATION_ACTIVE,
    METHOD_SIMULATION_HIGHSCORE_SNAPSHOT,
    METHOD_SIMULATION_HIGHSCORE_FRAMES,
    METHOD_SIMULATION_CANCEL,
    METHOD_SIMULATION_PAUSE,
    METHOD_SIMULATION_RESUME,
    METHOD_SIMULATION_SET_MOVE_DELAY,
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
        raise TypeError("Snake Lab response must be a JSON object")
    if response.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Snake Lab response has an unsupported protocol")
    if response.get("request_id") != request_id:
        raise ValueError("Snake Lab response request_id does not match")
    return response


class AsyncLabClient:
    """Serialize asynchronous requests over a ZeroMQ REQ connection."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout_ms: int = 3000,
    ) -> None:
        default_host, default_port = Network.destination("control")
        host = host if host is not None else default_host
        port = port if port is not None else default_port
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

    async def highscore_snapshot(self, run_id: str) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_HIGHSCORE_SNAPSHOT, {"run_id": run_id}
        )

    async def highscore_frames(self, run_id: str) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_HIGHSCORE_FRAMES, {"run_id": run_id}
        )

    async def submit(self, config: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            METHOD_SIMULATION_SUBMIT, {"config": config}
        )

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


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a simulation configuration from a local JSON object."""
    with config_path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise TypeError("Simulation config must be a JSON object")
    return config
