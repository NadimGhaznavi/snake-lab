import asyncio
import json
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import zmq

from snake_lab.client import AsyncLabClient, LabClient
from snake_lab.telemetry import (
    TOPIC_EPISODE,
    TOPIC_FRAME,
    TOPIC_RUN,
    FrameTelemetry,
    TelemetryEnvelope,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]


def available_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ZeroMQIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = available_tcp_port()
        self.telemetry_port = available_tcp_port()
        while self.telemetry_port == self.port:
            self.telemetry_port = available_tcp_port()
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
                "--telemetry-port",
                str(self.telemetry_port),
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

        self.client = LabClient(port=self.port, timeout_ms=3000)

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
        telemetry_context = zmq.Context()
        telemetry_socket = telemetry_context.socket(zmq.SUB)
        telemetry_socket.setsockopt(zmq.LINGER, 0)
        telemetry_socket.setsockopt(zmq.SUBSCRIBE, b"snake_lab.")
        telemetry_socket.connect(
            f"tcp://127.0.0.1:{self.telemetry_port}"
        )
        time.sleep(0.1)

        response = self.client.submit(
            {
                "epochs": 100,
                "seed": 7,
                "game": {
                    "board_width": 4,
                    "board_height": 1,
                    "initial_snake_length": 3,
                    "max_moves_multiplier": 1,
                },
                "model": {
                    "hidden_size": 8,
                    "layers": 1,
                    "dropout": 0,
                },
                "training": {
                    "sequence_length": 1,
                    "batch_size": 2,
                    "replay_max_frames": 100,
                },
            }
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["payload"]["state"], "queued")
        run_id = response["payload"]["run_id"]

        deadline = time.monotonic() + 10
        telemetry_messages = []
        while True:
            while telemetry_socket.poll(timeout=0):
                topic_bytes, payload_bytes = telemetry_socket.recv_multipart()
                envelope = TelemetryEnvelope.from_dict(
                    json.loads(payload_bytes.decode("utf-8"))
                )
                telemetry_messages.append(
                    (topic_bytes.decode("utf-8"), envelope)
                )
            status = self.client.status(run_id)
            if status["payload"]["state"] == "completed":
                break
            if time.monotonic() >= deadline:
                self.fail("Simulation did not complete")

        telemetry_deadline = time.monotonic() + 1
        while time.monotonic() < telemetry_deadline:
            if telemetry_socket.poll(timeout=20):
                topic_bytes, payload_bytes = telemetry_socket.recv_multipart()
                envelope = TelemetryEnvelope.from_dict(
                    json.loads(payload_bytes.decode("utf-8"))
                )
                telemetry_messages.append(
                    (topic_bytes.decode("utf-8"), envelope)
                )
                if (
                    topic_bytes.decode("utf-8") == TOPIC_RUN
                    and envelope.payload.get("state") == "completed"
                ):
                    break

        telemetry_socket.close()
        telemetry_context.term()

        self.assertEqual(status["payload"]["epochs"], 100)
        self.assertEqual(status["payload"]["completed_epochs"], 100)
        self.assertEqual(status["payload"]["total_steps"], 100)
        self.assertGreaterEqual(status["payload"]["high_score"], 0)
        self.assertEqual(status["payload"]["last_episode"]["episode"], 100)
        self.assertIsInstance(status["payload"]["last_episode"]["seed"], int)
        topics = {topic for topic, _envelope in telemetry_messages}
        self.assertEqual(
            topics,
            {TOPIC_RUN, TOPIC_FRAME, TOPIC_EPISODE},
        )
        frame_messages = [
            envelope
            for topic, envelope in telemetry_messages
            if topic == TOPIC_FRAME
        ]
        self.assertLess(len(frame_messages), 100)
        frame_envelope = frame_messages[0]
        frame = FrameTelemetry.from_dict(frame_envelope.payload)
        self.assertEqual(frame.board.width, 4)
        self.assertEqual(frame.board.height, 1)
        self.assertIn(
            "[Simulator] Simulation running on CPU",
            self.log_file.read_text(encoding="utf-8"),
        )

    def test_submit_uses_default_config(self) -> None:
        response = self.client.submit({})
        self.assertEqual(response["status"], "ok")
        run_id = response["payload"]["run_id"]

        status = self.client.status(run_id)
        self.assertEqual(status["payload"]["epochs"], 100)

    def test_invalid_config_is_rejected(self) -> None:
        response = self.client.submit({"epochs": 49})
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "invalid_config")

    def test_non_interactive_config_submission(self) -> None:
        config_file = Path(self.temp_dir.name) / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "epochs": 50,
                    "game": {
                        "board_width": 4,
                        "board_height": 1,
                        "initial_snake_length": 3,
                        "max_moves_multiplier": 1,
                    },
                    "model": {
                        "hidden_size": 8,
                        "layers": 1,
                        "dropout": 0,
                    },
                    "training": {
                        "sequence_length": 1,
                        "batch_size": 2,
                        "replay_max_frames": 100,
                    },
                }
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snake_lab.client",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "-c",
                str(config_file),
            ],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        response = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["payload"]["state"], "queued")

        run_id = response["payload"]["run_id"]
        cancelled = self.client.cancel(run_id)
        if cancelled["status"] == "ok":
            deadline = time.monotonic() + 2
            while self.client.status(run_id)["payload"]["state"] not in {
                "cancelled",
                "completed",
            }:
                if time.monotonic() >= deadline:
                    self.fail("CLI-submitted run did not stop")
                time.sleep(0.01)

    def test_human_runtime_controls(self) -> None:
        submitted = self.client.submit(
            {
                "epochs": 100,
                "seed": 17,
                "game": {
                    "board_width": 8,
                    "board_height": 8,
                    "initial_snake_length": 3,
                    "max_moves_multiplier": 10,
                },
                "model": {
                    "hidden_size": 8,
                    "layers": 1,
                    "dropout": 0,
                },
                "training": {
                    "sequence_length": 1,
                    "batch_size": 2,
                    "replay_max_frames": 100,
                },
            }
        )
        run_id = submitted["payload"]["run_id"]

        delayed = self.client.set_move_delay(run_id, 50)
        deadline = time.monotonic() + 2
        while self.client.status(run_id)["payload"]["state"] == "queued":
            if time.monotonic() >= deadline:
                self.fail("Delayed simulation did not start")
            time.sleep(0.01)
        paused = self.client.pause(run_id)
        time.sleep(0.1)
        before = self.client.status(run_id)["payload"]["completed_epochs"]
        time.sleep(0.15)
        after = self.client.status(run_id)["payload"]["completed_epochs"]
        active = asyncio.run(self._active_from_async_client())

        self.assertEqual(delayed["status"], "ok")
        self.assertEqual(delayed["payload"]["move_delay_ms"], 50)
        self.assertEqual(paused["payload"]["state"], "paused")
        self.assertEqual(before, after)
        self.assertEqual(active["payload"]["run"]["run_id"], run_id)
        self.assertEqual(active["payload"]["run"]["state"], "paused")

        resumed = self.client.resume(run_id)
        cancelling = self.client.cancel(run_id)
        self.assertEqual(resumed["payload"]["state"], "running")
        self.assertIn(
            cancelling["payload"]["state"], {"cancelling", "cancelled"}
        )

        deadline = time.monotonic() + 2
        while True:
            status = self.client.status(run_id)
            if status["payload"]["state"] == "cancelled":
                break
            if time.monotonic() >= deadline:
                self.fail("Runtime cancellation did not complete")
            time.sleep(0.01)

    async def _active_from_async_client(self) -> dict:
        client = AsyncLabClient(port=self.port)
        try:
            return await client.active()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
