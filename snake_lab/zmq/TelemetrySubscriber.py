"""ZeroMQ subscriber for SnakeLab live telemetry."""

from __future__ import annotations

import json

import zmq
import zmq.asyncio

from snake_lab.zmq.Protocol import TELEMETRY_TOPICS
from snake_lab.zmq.TelemetryEnvelope import TelemetryEnvelope


class TelemetrySubscriber:
    """Receive and validate selected SnakeLab telemetry topics."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        topics: tuple[str, ...] = TELEMETRY_TOPICS,
        context: zmq.asyncio.Context | None = None,
    ) -> None:
        self.endpoint = f"tcp://{host}:{port}"
        self._owns_context = context is None
        self._context = context or zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.setsockopt(zmq.RCVHWM, 100)
        for topic in topics:
            self._socket.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
        self._socket.connect(self.endpoint)

    async def receive(self) -> tuple[str, TelemetryEnvelope]:
        frames = await self._socket.recv_multipart()
        if len(frames) != 2:
            raise ValueError(
                f"telemetry expected two frames, received {len(frames)}"
            )
        topic = frames[0].decode("utf-8")
        if topic not in TELEMETRY_TOPICS:
            raise ValueError(f"unknown telemetry topic: {topic}")
        payload = json.loads(frames[1].decode("utf-8"))
        return topic, TelemetryEnvelope.from_dict(payload)

    def close(self) -> None:
        self._socket.close()
        if self._owns_context:
            self._context.term()
