"""ZeroMQ publication of simulation lifecycle events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import zmq
import zmq.asyncio

from snake_lab.event_protocol import EVENT_TOPICS, event_message


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

    def publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Validate and queue an event for asynchronous, best-effort delivery.

        Returning confirms local enqueueing, not subscriber receipt. Invalid
        events raise ProtocolError synchronously before entering the queue.
        """
        self._pending.put_nowait(event_message(event_type, payload))

    async def _publish_loop(self) -> None:
        while True:
            envelope = await self._pending.get()
            if envelope is None:
                return
            topic = EVENT_TOPICS[envelope["event_type"]].encode("utf-8")
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
