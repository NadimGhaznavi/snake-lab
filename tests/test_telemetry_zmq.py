import asyncio
import json
import unittest

import zmq
import zmq.asyncio

from snake_lab.game import Outcome
from snake_lab.telemetry import BoardSnapshot, FrameTelemetry, TOPIC_FRAME, TOPIC_RUN
from snake_lab.telemetry_zmq import TelemetryPublisher


class FakeSocket:
    def __init__(self) -> None:
        self.sent = []
        self.incoming = asyncio.Queue()

    def setsockopt(self, _option: int, _value: int) -> None:
        pass

    def bind(self, _endpoint: str) -> None:
        pass

    async def recv(self) -> bytes:
        return await self.incoming.get()

    async def send_multipart(self, frames: list[bytes]) -> None:
        self.sent.append(frames)

    def close(self) -> None:
        pass


class FakeContext:
    def __init__(self) -> None:
        self.socket_instance = FakeSocket()

    def socket(self, _socket_type: int) -> FakeSocket:
        return self.socket_instance


def frame(step: int) -> FrameTelemetry:
    return FrameTelemetry(
        episode=1,
        step=step,
        action=1,
        reward=0.0,
        done=False,
        outcome=Outcome.EMPTY,
        board=BoardSnapshot(
            width=4,
            height=1,
            snake_head=(step % 4, 0),
            snake_body=(),
            food=(3, 0),
            direction=(1, 0),
            score=0,
        ),
    )


class TelemetryPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostic_mode_preserves_every_offered_frame(self) -> None:
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context,
            address="127.0.0.1",
            port=41971,
            frame_rate=15,
        )
        publisher.start()
        context.socket_instance.incoming.put_nowait(b"\x01" + TOPIC_FRAME.encode())
        await asyncio.sleep(0)

        for step in (1, 2, 3):
            publisher.offer_frame("run-1", frame(step), preserve=True)
        await self._wait_for_messages(context.socket_instance, 3)
        await publisher.close()

        self.assertEqual(
            [
                json.loads(frames[1].decode("utf-8"))["payload"]["step"]
                for frames in context.socket_instance.sent
            ],
            [1, 2, 3],
        )

    async def test_full_speed_mode_keeps_only_the_latest_frame(self) -> None:
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context,
            address="127.0.0.1",
            port=41971,
            frame_rate=15,
        )
        publisher.start()
        context.socket_instance.incoming.put_nowait(b"\x01" + TOPIC_FRAME.encode())
        await asyncio.sleep(0)

        for step in (1, 2, 3):
            publisher.offer_frame("run-1", frame(step))
        await self._wait_for_messages(context.socket_instance, 1)
        await publisher.close()

        payload = json.loads(
            context.socket_instance.sent[0][1].decode("utf-8")
        )["payload"]
        self.assertEqual(payload["step"], 3)

    async def test_no_frame_interest_skips_serialization_but_keeps_run_events(self) -> None:
        from unittest.mock import patch

        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context, address="127.0.0.1", port=41971, frame_rate=15,
        )
        publisher.start()
        try:
            with patch.object(FrameTelemetry, "to_dict") as serialize:
                publisher.offer_frame("run-1", frame(1))
                publisher.offer_frame("run-1", frame(2), preserve=True)
                publisher.offer_run("run-1", {"state": "running"})
                await self._wait_for_messages(context.socket_instance, 1)
                serialize.assert_not_called()
            self.assertEqual(context.socket_instance.sent[0][0], TOPIC_RUN.encode())
            self.assertIsNone(publisher._latest_frame)
        finally:
            await publisher.close()

    async def test_last_unsubscribe_discards_pending_frames(self) -> None:
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context, address="127.0.0.1", port=41971, frame_rate=15,
        )
        publisher.start()
        try:
            context.socket_instance.incoming.put_nowait(b"\x01" + TOPIC_FRAME.encode())
            await asyncio.sleep(0)
            # Wake the subscription reader before either publishing task runs.
            context.socket_instance.incoming.put_nowait(b"\x00" + TOPIC_FRAME.encode())
            publisher.offer_frame("run-1", frame(1), preserve=True)
            publisher.offer_frame("run-1", frame(2))
            publisher.offer_run("run-1", {"state": "completed"})
            await self._wait_for_messages(context.socket_instance, 1)
            self.assertFalse(publisher.has_frame_subscribers)
            self.assertIsNone(publisher._latest_frame)
            self.assertEqual(
                [message[0] for message in context.socket_instance.sent],
                [TOPIC_RUN.encode()],
            )
        finally:
            await publisher.close()

    @staticmethod
    async def _wait_for_messages(socket: FakeSocket, count: int) -> None:
        for _attempt in range(100):
            if len(socket.sent) >= count:
                return
            await asyncio.sleep(0.001)
        raise AssertionError("Telemetry publisher did not send in time")


class SubscriptionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.context = zmq.asyncio.Context()
        self.publisher = TelemetryPublisher(
            context=self.context, address="127.0.0.1", port=0, frame_rate=100,
        )
        self.publisher.endpoint = "inproc://telemetry-demand"
        self.publisher.start()
        self.subscribers = []

    async def asyncTearDown(self) -> None:
        for subscriber in self.subscribers:
            subscriber.close(linger=0)
        await self.publisher.close()
        self.context.term()

    def subscribe(self, prefix: bytes):
        subscriber = self.context.socket(zmq.SUB)
        subscriber.setsockopt(zmq.SUBSCRIBE, prefix)
        subscriber.connect(self.publisher.endpoint)
        self.subscribers.append(subscriber)
        return subscriber

    async def wait_for_interest(self, expected: bool) -> None:
        async def wait():
            while self.publisher.has_frame_subscribers != expected:
                self.publisher.check()
                await asyncio.sleep(0.001)
        await asyncio.wait_for(wait(), 2)

    async def receive_frame(self, subscriber) -> None:
        self.publisher.offer_frame("run-1", frame(1), preserve=True)
        message = await asyncio.wait_for(subscriber.recv_multipart(), 2)
        self.assertEqual(message[0], TOPIC_FRAME.encode())

    async def test_two_viewers_disconnect_and_reconnect(self) -> None:
        self.assertFalse(self.publisher.has_frame_subscribers)
        first = self.subscribe(TOPIC_FRAME.encode())
        await self.wait_for_interest(True)
        await self.receive_frame(first)
        second = self.subscribe(TOPIC_FRAME.encode())
        # Receipt proves the second subscription reached XPUB before closing first.
        await self.receive_frame(second)
        first.close(linger=0)
        await asyncio.sleep(0.02)
        self.assertTrue(self.publisher.has_frame_subscribers)
        await self.receive_frame(second)
        second.close(linger=0)
        await self.wait_for_interest(False)
        third = self.subscribe(TOPIC_FRAME.encode())
        await self.wait_for_interest(True)
        await self.receive_frame(third)

    async def test_prefix_and_wildcard_filters_and_unsubscribe(self) -> None:
        other = self.subscribe(TOPIC_RUN.encode())
        self.publisher.offer_run("run-1", {"state": "running"})
        await asyncio.wait_for(other.recv_multipart(), 2)
        self.assertFalse(self.publisher.has_frame_subscribers)
        prefix = self.subscribe(b"snake_lab.")
        await self.wait_for_interest(True)
        await self.receive_frame(prefix)
        wildcard = self.subscribe(b"")
        await self.receive_frame(wildcard)
        prefix.setsockopt(zmq.UNSUBSCRIBE, b"snake_lab.")
        await asyncio.sleep(0.02)
        self.assertTrue(self.publisher.has_frame_subscribers)
        wildcard.setsockopt(zmq.UNSUBSCRIBE, b"")
        await self.wait_for_interest(False)


if __name__ == "__main__":
    unittest.main()
