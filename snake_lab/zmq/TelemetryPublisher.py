"""ZeroMQ publisher for SnakeLab live telemetry."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

import zmq
import zmq.asyncio

from snake_lab.zmq.Protocol import TOPIC_EPISODE, TOPIC_FRAME, TOPIC_RUN
from snake_lab.zmq.FrameTelemetry import FrameTelemetry
from snake_lab.zmq.TelemetryEnvelope import TelemetryEnvelope


class TelemetryPublisher:
    """Publish best-effort telemetry in retained queue order.

    Overflow drops the oldest queued message, regardless of topic. Shutdown
    discards pending messages. Lifecycle notifications use EventsPublisher.
    """

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        address: str,
        port: int,
        event_queue_size: int = 1024,
    ) -> None:
        if event_queue_size <= 0:
            raise ValueError("event_queue_size must be greater than zero")

        self.endpoint = f"tcp://{address}:{port}"
        self._socket = context.socket(zmq.XPUB)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.setsockopt(zmq.SNDHWM, event_queue_size)
        self._events: asyncio.Queue[tuple[str, str, dict[str, Any]]] = (
            asyncio.Queue(maxsize=event_queue_size)
        )
        self._sequences: defaultdict[str, int] = defaultdict(int)
        self._event_task: asyncio.Task[None] | None = None
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

    def check(self) -> None:
        """Surface failed telemetry tasks to the server service loop."""
        for task in (self._subscription_task, self._event_task):
            if task is not None and task.done():
                task.result()
                raise RuntimeError("telemetry publisher stopped unexpectedly")

    def offer_frame(
        self,
        run_id: str,
        frame: FrameTelemetry,
    ) -> None:
        """Queue each frame immediately when a viewer is subscribed."""
        if not self.has_frame_subscribers:
            return
        self._offer_event(TOPIC_FRAME, run_id, frame.to_dict())

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

    async def close(self) -> None:
        tasks = [
            task
            for task in (self._event_task, self._subscription_task)
            if task is not None
        ]
        self._subscription_task = None
        self._event_task = None
        for task in tasks:
            task.cancel()
        try:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                for task in tasks:
                    if not task.cancelled():
                        task.result()
        finally:
            self._socket.close()
            self._frame_filters.clear()
            self._has_frame_subscribers = False
            self._started = False
