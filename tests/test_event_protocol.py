import unittest

from snake_lab.event_protocol import (
    EVENT_PROTOCOL_VERSION,
    EVENT_SIMULATION_ENDED,
    event_message,
    parse_event,
)
from snake_lab.protocol import ProtocolError


class EventProtocolTests(unittest.TestCase):
    def test_terminal_results_round_trip(self) -> None:
        for state in ("completed", "failed", "cancelled"):
            with self.subTest(state=state):
                payload = {"run_id": "run-1", "state": state}
                if state == "failed":
                    payload["error"] = "test failure"
                expected = {
                    "protocol_version": EVENT_PROTOCOL_VERSION,
                    "event_type": EVENT_SIMULATION_ENDED,
                    "payload": payload,
                }
                self.assertEqual(event_message(EVENT_SIMULATION_ENDED, payload), expected)
                self.assertEqual(parse_event(expected), expected)

    def test_rejects_invalid_payloads(self) -> None:
        for payload in (
            None, [], {}, {"run_id": "x"}, {"state": "completed"},
            {"run_id": "", "state": "completed"},
            {"run_id": 1, "state": "completed"},
            {"run_id": "x", "state": "cancelling"},
            {"run_id": "x", "state": []},
            {"run_id": "x", "state": "failed", "error": None},
            {"run_id": "x", "state": "failed", "error": 1},
            {"run_id": "x", "state": "completed", "extra": True},
        ):
            with self.subTest(payload=payload), self.assertRaises(ProtocolError) as raised:
                event_message(EVENT_SIMULATION_ENDED, payload)
            self.assertEqual(raised.exception.code, "invalid_event")

    def test_rejects_unknown_event_types(self) -> None:
        for event_type in ("unknown", "", None, []):
            with self.subTest(event_type=event_type), self.assertRaises(ProtocolError) as raised:
                event_message(event_type, {"run_id": "x", "state": "completed"})
            self.assertEqual(raised.exception.code, "unknown_event")

    def test_rejects_invalid_envelopes_and_old_version(self) -> None:
        valid = event_message(EVENT_SIMULATION_ENDED, {"run_id": "x", "state": "completed"})
        for data in (
            None, [], {}, {**valid, "run_id": "x"},
            {**valid, "protocol_version": 1},
            {**valid, "protocol_version": 2.0},
            {**valid, "event_type": "unknown"},
            {**valid, "payload": {}},
            {"protocol_version": 1, "run_id": "x", "payload": {"state": "completed"}},
        ):
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                parse_event(data)
