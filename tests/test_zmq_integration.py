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
        self.log_file = Path(self.temp_dir.name) / "server.log"
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
                str(self.log_file),
            ],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        startup_message = (
            f"SnakeLab server listening on tcp://127.0.0.1:{self.port}"
        )
        deadline = time.monotonic() + 10
        while True:
            if self.server.poll() is not None:
                stdout, stderr = self.server.communicate(timeout=1)
                self.fail(f"Server failed to start: {stdout}{stderr}")
            if self.log_file.exists() and startup_message in (
                self.log_file.read_text(encoding="utf-8")
            ):
                break
            if time.monotonic() >= deadline:
                self.server.terminate()
                stdout, stderr = self.server.communicate(timeout=2)
                self.fail(f"Server startup timed out: {stdout}{stderr}")
            time.sleep(0.05)

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
        response = self.client.submit({"epochs": 100})
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

        self.assertEqual(status["payload"]["epochs"], 100)
        self.assertEqual(status["payload"]["completed_epochs"], 100)
        self.assertIn(
            "[Simulator] Simulation running on CPU",
            self.log_file.read_text(encoding="utf-8"),
        )

    def test_submit_uses_default_config(self) -> None:
        response = self.client.submit({})
        self.assertEqual(response["status"], "ok")
        run_id = response["payload"]["run_id"]

        status = self.client.status(run_id)
        self.assertEqual(status["payload"]["epochs"], 1500)

    def test_invalid_config_is_rejected(self) -> None:
        response = self.client.submit({"epochs": 99})
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "invalid_config")


if __name__ == "__main__":
    unittest.main()
