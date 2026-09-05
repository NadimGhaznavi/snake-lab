import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock

import zmq

from snake_lab.events_zmq import EventsPublisher, TOPIC_SIMULATION_ENDED
from snake_lab.protocol import PROTOCOL_VERSION


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
        self.publisher.offer_simulation_ended("first", "completed")
        self.publisher.offer_simulation_ended("second", "failed", "test failure")
        self.publisher.offer_simulation_ended("third", "cancelled")

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
                    "protocol_version": PROTOCOL_VERSION,
                    "run_id": run_id,
                    "payload": payload,
                },
            )
        self.socket.close.assert_called_once()

    async def test_transport_failure_is_reported_and_socket_closes(self) -> None:
        self.socket.send_multipart.side_effect = zmq.ZMQError("send failed")
        self.publisher.start()
        self.publisher.offer_simulation_ended("run-1", "completed")
        await asyncio.sleep(0)

        with self.assertRaisesRegex(zmq.ZMQError, "send failed"):
            self.publisher.check()
        with self.assertRaisesRegex(zmq.ZMQError, "send failed"):
            await asyncio.wait_for(self.publisher.close(), 1)
        self.socket.close.assert_called_once()

    async def test_close_without_start_releases_socket(self) -> None:
        await self.publisher.close()
        self.socket.close.assert_called_once()
        self.socket.send_multipart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
