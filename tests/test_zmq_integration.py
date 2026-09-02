import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from snake_lab.client import LabClient


PROJECT_DIR = Path(__file__).resolve().parents[1]


def available_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ZeroMQIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = available_tcp_port()
        self.temp_dir = tempfile.TemporaryDirectory()
        log_file = str(Path(self.temp_dir.name) / "server.log")
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "snake_lab.server",
                "--address",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-file",
                log_file,
            ],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        startup = self.server.stdout.readline()
        if startup != (
            f"SnakeLab server listening on tcp://127.0.0.1:{self.port}\n"
        ):
            _, stderr = self.server.communicate(timeout=1)
            self.fail(f"Server failed to start: {startup}{stderr}")

        self.client = LabClient(port=self.port, timeout_ms=1000)

    def tearDown(self) -> None:
        self.client.close()
        self.server.send_signal(signal.SIGTERM)
        self.server.wait(timeout=2)
        self.server.stdout.close()
        self.server.stderr.close()
        self.temp_dir.cleanup()
        self.assertEqual(self.server.returncode, 0)

    def test_health_request(self) -> None:
        response = self.client.health()
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["payload"], {"service": "snake-lab"})

    def test_submit_and_complete_simulation(self) -> None:
        response = self.client.submit(
            {"schema_version": 1, "name": "integration", "epochs": 25}
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["payload"]["state"], "queued")
        run_id = response["payload"]["run_id"]

        deadline = time.monotonic() + 1
        while True:
            status = self.client.status(run_id)
            if status["payload"]["state"] == "completed":
                break
            if time.monotonic() >= deadline:
                self.fail("Simulation did not complete")

        self.assertEqual(status["payload"]["epochs"], 25)
        self.assertEqual(status["payload"]["completed_epochs"], 25)

    def test_invalid_config_is_rejected(self) -> None:
        response = self.client.submit(
            {"schema_version": 1, "name": "invalid", "epochs": 0}
        )
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "invalid_config")


if __name__ == "__main__":
    unittest.main()
