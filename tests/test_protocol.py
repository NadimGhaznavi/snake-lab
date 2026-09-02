import unittest

from snake_lab.server import SnakeLabServer


class ServerProtocolTests(unittest.TestCase):
    def test_health(self) -> None:
        self.assertEqual(
            SnakeLabServer.handle_message("health"), {"status": "ok"}
        )

    def test_unknown_message(self) -> None:
        self.assertEqual(
            SnakeLabServer.handle_message("unknown"),
            {"status": "error", "error": "unknown message"},
        )


if __name__ == "__main__":
    unittest.main()
