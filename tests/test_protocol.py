import unittest

from snake_lab.protocol import PROTOCOL_VERSION, ProtocolError, Request
from snake_lab.server import SnakeLabServer


class RequestTests(unittest.TestCase):
    def test_valid_request(self) -> None:
        request = Request.from_dict(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": "request-1",
                "method": "health",
                "payload": {},
            }
        )
        self.assertEqual(request.method, "health")

    def test_extra_field_is_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            Request.from_dict(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "request-1",
                    "method": "health",
                    "payload": {},
                    "extra": True,
                }
            )


class ConfigValidationTests(unittest.TestCase):
    def test_valid_config(self) -> None:
        config = {"schema_version": 1, "name": "test", "epochs": 10}
        self.assertEqual(SnakeLabServer.validate_config(config), config)

    def test_non_positive_epochs_are_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            SnakeLabServer.validate_config(
                {"schema_version": 1, "name": "test", "epochs": 0}
            )

    def test_unknown_config_field_is_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            SnakeLabServer.validate_config(
                {
                    "schema_version": 1,
                    "name": "test",
                    "epochs": 10,
                    "unknown": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
