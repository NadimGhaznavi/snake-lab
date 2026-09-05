import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock

import zmq

from snake_lab.events_zmq import EventsPublisher
from snake_lab.event_protocol import (
    EVENT_PROTOCOL_VERSION,
    EVENT_SIMULATION_ENDED,
    TOPIC_SIMULATION_ENDED,
)
from snake_lab.protocol import ProtocolError


class EventsPublisherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.socket = Mock()
        self.socket.send_multipart = AsyncMock()
        self.publisher = EventsPublisher(
            context=Mock(socket=Mock(return_value=self.socket)),
            address="127.0.0.1",
            port=41972,
        )

    async def test_close_sends_all_pending_terminal_events_in_order(self) -> None:
        self.publisher.start()
        self.publisher.publish_event(EVENT_SIMULATION_ENDED, {"run_id": "first", "state": "completed"})
        self.publisher.publish_event(EVENT_SIMULATION_ENDED, {"run_id": "second", "state": "failed", "error": "test failure"})
        self.publisher.publish_event(EVENT_SIMULATION_ENDED, {"run_id": "third", "state": "cancelled"})

        # Close before giving the background publisher a turn.
        await asyncio.wait_for(self.publisher.close(), 1)

        expected = [
            ("first", {"state": "completed"}),
            ("second", {"state": "failed", "error": "test failure"}),
            ("third", {"state": "cancelled"}),
        ]
        sent = self.socket.send_multipart.call_args_list
        self.assertEqual(len(sent), len(expected))
        for invocation, (run_id, payload) in zip(sent, expected):
            topic, encoded = invocation.args[0]
            self.assertEqual(topic, TOPIC_SIMULATION_ENDED.encode("utf-8"))
            self.assertEqual(
                json.loads(encoded),
                {
                    "protocol_version": EVENT_PROTOCOL_VERSION,
                    "event_type": EVENT_SIMULATION_ENDED,
                    "payload": {"run_id": run_id, **payload},
                },
            )
        self.socket.close.assert_called_once()

    async def test_transport_failure_is_reported_and_socket_closes(self) -> None:
        self.socket.send_multipart.side_effect = zmq.ZMQError("send failed")
        self.publisher.start()
        self.publisher.publish_event(EVENT_SIMULATION_ENDED, {"run_id": "run-1", "state": "completed"})
        await asyncio.sleep(0)

        with self.assertRaisesRegex(zmq.ZMQError, "send failed"):
            self.publisher.check()
        with self.assertRaisesRegex(zmq.ZMQError, "send failed"):
            await asyncio.wait_for(self.publisher.close(), 1)
        self.socket.close.assert_called_once()

    async def test_invalid_event_is_rejected_before_enqueueing(self) -> None:
        with self.assertRaises(ProtocolError):
            self.publisher.publish_event(EVENT_SIMULATION_ENDED, {"run_id": "x", "state": "running"})
        self.assertTrue(self.publisher._pending.empty())
        await self.publisher.close()

    async def test_publish_snapshots_the_callers_payload(self) -> None:
        self.publisher.start()
        payload = {"run_id": "original", "state": "completed"}
        self.publisher.publish_event(EVENT_SIMULATION_ENDED, payload)
        payload["run_id"] = "changed"
        await self.publisher.close()
        message = json.loads(self.socket.send_multipart.call_args.args[0][1])
        self.assertEqual(message["payload"]["run_id"], "original")

    async def test_close_without_start_releases_socket(self) -> None:
        await self.publisher.close()
        self.socket.close.assert_called_once()
        self.socket.send_multipart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
