"""ZeroMQ request/reply server for SnakeLab."""

import argparse
import json
import signal
import threading
from typing import Any

import zmq

from constants.DSnakeLab import DSnakeLab
from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from utils.MyLog import MyLog


class SnakeLabServer:
    """Listen for SnakeLab control requests over ZeroMQ."""

    def __init__(
        self,
        address: str = "*",
        port: int = DSnakeLab.PORT,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
    ) -> None:
        self.endpoint = f"tcp://{address}:{port}"
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.REP)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._stop_event = threading.Event()
        self.log = MyLog(
            client_id=DModule.SERVER,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
        )

    def stop(self) -> None:
        """Request a clean shutdown of the server loop."""
        self._stop_event.set()

    @staticmethod
    def handle_message(message: str) -> dict[str, Any]:
        """Return the response for a control message."""
        if message.strip().lower() == "health":
            return {"status": "ok"}
        return {"status": "error", "error": "unknown message"}

    def run(self) -> None:
        """Bind the REP socket and process requests until stopped."""
        self._socket.bind(self.endpoint)
        print(f"SnakeLab server listening on {self.endpoint}", flush=True)
        self.log.info(f"SnakeLab server listening on {self.endpoint}")

        try:
            while not self._stop_event.is_set():
                if self._socket.poll(timeout=500) == 0:
                    continue

                message = self._socket.recv_string()
                response = self.handle_message(message)
                self._socket.send_string(
                    json.dumps(response, separators=(",", ":"))
                )
        finally:
            self._socket.close()
            self._context.term()
            self.log.shutdown()


def main() -> None:
    """Run the SnakeLab server process."""
    parser = argparse.ArgumentParser(description="Run the SnakeLab server")
    parser.add_argument("--address", default="*")
    parser.add_argument("--port", type=int, default=DSnakeLab.PORT)
    parser.add_argument("--log-file", default=DSnakeLab.SERVER_LOG_FILE)
    args = parser.parse_args()

    server = SnakeLabServer(
        address=args.address,
        port=args.port,
        log_file=args.log_file,
    )

    def request_stop(_signum: int, _frame: Any) -> None:
        server.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    server.run()


if __name__ == "__main__":
    main()
