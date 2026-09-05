"""ZeroMQ transport for SnakeLab live telemetry."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

import zmq
import zmq.asyncio

from snake_lab.telemetry import (
    TELEMETRY_TOPICS,
    TOPIC_EPISODE,
    TOPIC_FRAME,
    TOPIC_RUN,
    FrameTelemetry,
    TelemetryEnvelope,
)


class TelemetryPublisher:
    """Publish low-rate events and the latest frame at a bounded rate."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        address: str,
        port: int,
        frame_rate: float,
        event_queue_size: int = 1024,
    ) -> None:
        if frame_rate <= 0:
            raise ValueError("frame_rate must be greater than zero")
        if event_queue_size <= 0:
            raise ValueError("event_queue_size must be greater than zero")

        self.endpoint = f"tcp://{address}:{port}"
        self._frame_interval = 1.0 / frame_rate
        self._socket = context.socket(zmq.XPUB)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.setsockopt(zmq.SNDHWM, event_queue_size)
        self._events: asyncio.Queue[tuple[str, str, dict[str, Any]]] = (
            asyncio.Queue(maxsize=event_queue_size)
        )
        self._latest_frame: tuple[str, FrameTelemetry] | None = None
        self._frame_ready = asyncio.Event()
        self._sequences: defaultdict[str, int] = defaultdict(int)
        self._event_task: asyncio.Task[None] | None = None
        self._frame_task: asyncio.Task[None] | None = None
        self._started = False
        self._frame_filters: set[bytes] = set()
        self._has_frame_subscribers = False
        self._subscription_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._started:
            return
        self._socket.bind(self.endpoint)
        self._subscription_task = asyncio.create_task(
            self._subscription_loop(), name="telemetry-subscriptions"
        )
        self._event_task = asyncio.create_task(
            self._event_loop(), name="telemetry-events"
        )
        self._frame_task = asyncio.create_task(
            self._frame_loop(), name="telemetry-frames"
        )
        self._started = True

    @property
    def has_frame_subscribers(self) -> bool:
        """Whether a subscription filter currently matches the frame topic."""
        return self._has_frame_subscribers

    async def _subscription_loop(self) -> None:
        # Default XPUB reports the first subscribe and last unsubscribe for
        # each filter, including disconnections. Do not enable XPUB_VERBOSE:
        # a set relies on these aggregated notifications, not per-client counts.
        topic = TOPIC_FRAME.encode("utf-8")
        while True:
            message = await self._socket.recv()
            if not message or message[0] not in (0, 1):
                continue
            prefix = message[1:]
            if not topic.startswith(prefix):
                continue
            if message[0] == 1:
                self._frame_filters.add(prefix)
            else:
                self._frame_filters.discard(prefix)
            self._has_frame_subscribers = bool(self._frame_filters)
            if not self._has_frame_subscribers:
                self._latest_frame = None
                self._frame_ready.clear()

    def check(self) -> None:
        """Surface failed telemetry tasks to the server service loop."""
        for task in (self._subscription_task, self._event_task, self._frame_task):
            if task is not None and task.done():
                task.result()
                raise RuntimeError("telemetry publisher stopped unexpectedly")

    def offer_frame(
        self,
        run_id: str,
        frame: FrameTelemetry,
        *,
        preserve: bool = False,
    ) -> None:
        """Offer a sampled frame, or preserve it in diagnostic mode."""
        if not isinstance(frame, FrameTelemetry):
            raise TypeError("frame must be FrameTelemetry")
        if not self.has_frame_subscribers:
            return
        if preserve:
            self._latest_frame = None
            self._frame_ready.clear()
            self._offer_event(TOPIC_FRAME, run_id, frame.to_dict())
            return
        self._latest_frame = (run_id, frame)
        self._frame_ready.set()

    def offer_run(self, run_id: str, payload: dict[str, Any]) -> None:
        self._offer_event(TOPIC_RUN, run_id, payload)

    def offer_episode(self, run_id: str, payload: dict[str, Any]) -> None:
        self._offer_event(TOPIC_EPISODE, run_id, payload)

    def _offer_event(
        self, topic: str, run_id: str, payload: dict[str, Any]
    ) -> None:
        event = (topic, run_id, payload)
        try:
            self._events.put_nowait(event)
        except asyncio.QueueFull:
            self._events.get_nowait()
            self._events.task_done()
            self._events.put_nowait(event)

    async def _send(
        self, topic: str, run_id: str, payload: dict[str, Any]
    ) -> None:
        if topic == TOPIC_FRAME and not self.has_frame_subscribers:
            return
        sequence = self._sequences[topic]
        self._sequences[topic] += 1
        envelope = TelemetryEnvelope(sequence, run_id, payload)
        encoded = json.dumps(
            envelope.to_dict(), separators=(",", ":")
        ).encode("utf-8")
        await self._socket.send_multipart([topic.encode("utf-8"), encoded])

    async def _event_loop(self) -> None:
        while True:
            topic, run_id, payload = await self._events.get()
            try:
                await self._send(topic, run_id, payload)
            finally:
                self._events.task_done()

    async def _frame_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_send = loop.time()
        while True:
            await self._frame_ready.wait()
            delay = next_send - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

            pending = self._latest_frame
            self._latest_frame = None
            self._frame_ready.clear()
            if pending is None or not self.has_frame_subscribers:
                continue
            run_id, frame = pending
            self._offer_event(TOPIC_FRAME, run_id, frame.to_dict())
            next_send = loop.time() + self._frame_interval

            if self._latest_frame is not None:
                self._frame_ready.set()

    async def close(self) -> None:
        tasks = [
            task
            for task in (self._event_task, self._frame_task, self._subscription_task)
            if task is not None
        ]
        self._subscription_task = None
        self._event_task = None
        self._frame_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._socket.close()
        self._frame_filters.clear()
        self._has_frame_subscribers = False
        self._latest_frame = None
        self._frame_ready.clear()
        self._started = False


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
