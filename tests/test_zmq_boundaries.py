"""Transport failure propagation, queue policy, and subscriber ownership."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from snake_lab.server.SnakeLabServer import SnakeLabServer
from snake_lab.zmq.Protocol import TOPIC_RUN, TOPIC_FRAME, ProtocolError
from snake_lab.zmq.TelemetryEnvelope import TelemetryEnvelope
from snake_lab.zmq.TelemetryPublisher import TelemetryPublisher
from snake_lab.zmq.TelemetrySubscriber import TelemetrySubscriber
from tests.test_telemetry_zmq import FakeContext, frame


class PublisherBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_overflow_drops_oldest_regardless_of_topic(self):
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context, address="127.0.0.1", port=41971, event_queue_size=2,
        )
        publisher.start()
        context.socket_instance.incoming.put_nowait(b"\x01" + TOPIC_FRAME.encode())
        await asyncio.sleep(0)
        try:
            publisher.offer_run("r", {"state": "running"})
            publisher.offer_episode("r", {"episode": 1})
            publisher.offer_frame("r", frame(1))
            publisher.offer_frame("r", frame(2))
            await asyncio.wait_for(publisher._events.join(), 1)
            sent = context.socket_instance.sent
            self.assertEqual([topic.decode() for topic, _ in sent], [TOPIC_FRAME] * 2)
            self.assertEqual([json.loads(data)["payload"]["step"] for _, data in sent], [1, 2])
            self.assertEqual([json.loads(data)["sequence"] for _, data in sent], [0, 1])
        finally:
            await publisher.close()

    async def test_close_propagates_send_and_subscription_failures(self):
        for operation in ("send_multipart", "recv"):
            with self.subTest(operation=operation):
                context = FakeContext()
                failure = RuntimeError(f"{operation} failed")
                setattr(context.socket_instance, operation, AsyncMock(side_effect=failure))
                context.socket_instance.close = Mock()
                publisher = TelemetryPublisher(context=context, address="127.0.0.1", port=41971)
                publisher.start()
                tasks = (publisher._event_task, publisher._subscription_task)
                publisher.offer_run("r", {"state": "running"})
                await asyncio.sleep(0)
                with self.assertRaises(RuntimeError) as raised:
                    await publisher.close()
                self.assertIs(raised.exception, failure)
                self.assertTrue(all(task.done() for task in tasks))
                context.socket_instance.close.assert_called_once_with()
                self.assertFalse(publisher.has_frame_subscribers)

    async def test_normal_close_cancels_tasks_and_discards_pending_delivery(self):
        context = FakeContext()
        publisher = TelemetryPublisher(context=context, address="127.0.0.1", port=41971)
        publisher.start()
        tasks = (publisher._event_task, publisher._subscription_task)
        publisher.offer_episode("r", {"episode": 1})
        await publisher.close()
        self.assertTrue(all(task.cancelled() for task in tasks))
        self.assertEqual(context.socket_instance.sent, [])


class SubscriberBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.socket = Mock(recv_multipart=AsyncMock())
        self.context = Mock(socket=Mock(return_value=self.socket))
        self.subscriber = TelemetrySubscriber(host="localhost", port=41971, context=self.context)
        self.addCleanup(self.subscriber.close)

    async def test_decodes_valid_message(self):
        envelope = TelemetryEnvelope(7, "r", {"state": "running"})
        self.socket.recv_multipart.return_value = [TOPIC_RUN.encode(), json.dumps(envelope.to_dict()).encode()]
        self.assertEqual(await self.subscriber.receive(), (TOPIC_RUN, envelope))

    async def test_rejects_bad_framing_encoding_json_and_envelopes(self):
        for frames, error in (
            ([b"only-one"], ValueError),
            ([b"unknown", b"{}"], ValueError),
            ([b"\xff", b"{}"], UnicodeDecodeError),
            ([TOPIC_RUN.encode(), b"\xff"], UnicodeDecodeError),
            ([TOPIC_RUN.encode(), b"not json"], json.JSONDecodeError),
            ([TOPIC_RUN.encode(), b"{}"], ProtocolError),
        ):
            with self.subTest(frames=frames):
                self.socket.recv_multipart.return_value = frames
                with self.assertRaises(error):
                    await self.subscriber.receive()

    def test_close_preserves_shared_context(self):
        self.subscriber.close()
        self.socket.close.assert_called_once_with()
        self.context.term.assert_not_called()

    def test_close_terminates_owned_context_after_socket(self):
        order = []
        self.socket.close.side_effect = lambda: order.append("socket")
        self.context.term.side_effect = lambda: order.append("context")
        with patch("snake_lab.zmq.TelemetrySubscriber.zmq.asyncio.Context", return_value=self.context):
            subscriber = TelemetrySubscriber(host="localhost", port=41971)
        subscriber.close()
        self.assertEqual(order, ["socket", "context"])


class ServerCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_telemetry_failure_still_closes_socket_context_and_store(self):
        server = SnakeLabServer.__new__(SnakeLabServer)
        server.endpoint = "unused"
        server._socket = Mock()
        server._context = Mock()
        server._stop_event = asyncio.Event()
        server._stop_event.set()
        server._worker_loop = AsyncMock()
        server._shutdown_worker = AsyncMock()
        failure = RuntimeError("telemetry failed")
        server.telemetry = Mock(close=AsyncMock(side_effect=failure))
        server.events = Mock(close=AsyncMock())
        server.store = Mock()
        server.log = Mock()
        order = []
        server._socket.close.side_effect = lambda: order.append("socket")
        server._context.term.side_effect = lambda: order.append("context")
        server.store.close.side_effect = lambda: order.append("store")
        try:
            with self.assertRaises(RuntimeError) as raised:
                await server.run()
            self.assertIs(raised.exception, failure)
            self.assertEqual(order, ["socket", "context", "store"])
            server.events.close.assert_awaited_once()
        finally:
            await server._worker_task
