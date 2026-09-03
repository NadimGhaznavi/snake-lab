import unittest

from snake_lab.protocol import PROTOCOL_VERSION, ProtocolError, Request


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

if __name__ == "__main__":
    unittest.main()
