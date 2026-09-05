"""ZeroMQ publication of simulation lifecycle events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import zmq
import zmq.asyncio

from snake_lab.protocol import PROTOCOL_VERSION


TOPIC_SIMULATION_ENDED = "snake_lab.simulation.ended"


class EventsPublisher:
    """Send individual lifecycle notifications independently of telemetry."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        address: str,
        port: int,
    ) -> None:
        self.endpoint = f"tcp://{address}:{port}"
        self._socket = context.socket(zmq.PUB)
        # Allow already-sent terminal events a bounded time to leave on exit.
        self._socket.setsockopt(zmq.LINGER, 1000)
        self._pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._socket.bind(self.endpoint)
        self._task = asyncio.create_task(
            self._publish_loop(), name="simulation-events"
        )

    def offer_simulation_ended(
        self, run_id: str, state: str, error: str | None = None
    ) -> None:
        """Queue a notification after the terminal state has been stored."""
        if state not in {"completed", "failed", "cancelled"}:
            raise ValueError("simulation ended requires a terminal state")
        payload = {"state": state}
        if error is not None:
            payload["error"] = error
        self._pending.put_nowait(
            {
                "protocol_version": PROTOCOL_VERSION,
                "run_id": run_id,
                "payload": payload,
            }
        )

    async def _publish_loop(self) -> None:
        topic = TOPIC_SIMULATION_ENDED.encode("utf-8")
        while True:
            envelope = await self._pending.get()
            if envelope is None:
                return
            encoded = json.dumps(
                envelope, separators=(",", ":")
            ).encode("utf-8")
            await self._socket.send_multipart(
                [topic, encoded], flags=zmq.DONTWAIT
            )

    def check(self) -> None:
        """Surface transport failures to the server's service loop."""
        if self._task is not None and self._task.done():
            self._task.result()
            raise RuntimeError("events publisher stopped unexpectedly")

    async def close(self) -> None:
        """Send pending notifications before closing the publisher."""
        try:
            if self._task is not None:
                self._pending.put_nowait(None)
                await self._task
        finally:
            self._task = None
            self._socket.close()
