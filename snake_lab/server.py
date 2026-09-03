"""ZeroMQ request/reply server for SnakeLab."""

import argparse
import queue
import signal
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import zmq

from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DSnakeLab import DSnakeLab
from snake_lab.configuration import (
    ConfigurationError,
    simulation_config_template,
)
from snake_lab.protocol import (
    METHOD_HEALTH,
    METHOD_SIMULATION_STATUS,
    METHOD_SIMULATION_SUBMIT,
    ProtocolError,
    Request,
    error_response,
    success_response,
)
from snake_lab.simulator import Simulator
from utils.MyLog import MyLog


@dataclass(slots=True)
class SimulationRun:
    run_id: str
    config: dict[str, Any]
    state: str = "queued"
    completed_epochs: int = 0


class SnakeLabServer:
    """Accept and execute SnakeLab simulation requests."""

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
        self._run_queue: queue.Queue[SimulationRun | None] = queue.Queue()
        self._runs: dict[str, SimulationRun] = {}
        self._config_template = simulation_config_template()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="simulation-worker",
        )
        self.log = MyLog(
            client_id=DModule.SERVER,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )

    def stop(self) -> None:
        self._stop_event.set()

    def validate_config(self, config: Any) -> dict[str, Any]:
        try:
            return self._config_template.resolve(config)
        except ConfigurationError as error:
            raise ProtocolError("invalid_config", str(error)) from error

    def _submit(self, request: Request) -> dict[str, Any]:
        if set(request.payload) != {"config"}:
            raise ProtocolError(
                "invalid_request", "submit payload must contain only config"
            )

        config = self.validate_config(request.payload["config"])
        run = SimulationRun(run_id=str(uuid.uuid4()), config=config)
        self._runs[run.run_id] = run
        queue_position = self._run_queue.qsize() + 1
        response = success_response(
            request.request_id,
            {
                "run_id": run.run_id,
                "state": "queued",
                "queue_position": queue_position,
            },
        )
        self._run_queue.put(run)
        self.log.info(
            f"Queued simulation {run.run_id}: {config['epochs']} epochs"
        )
        return response

    def _status(self, request: Request) -> dict[str, Any]:
        if set(request.payload) != {"run_id"}:
            raise ProtocolError(
                "invalid_request", "status payload must contain only run_id"
            )
        run_id = request.payload["run_id"]
        if not isinstance(run_id, str) or not run_id:
            raise ProtocolError(
                "invalid_request", "run_id must be a non-empty string"
            )
        if run_id not in self._runs:
            raise ProtocolError("run_not_found", f"Unknown run: {run_id}")

        run = self._runs[run_id]
        return success_response(
            request.request_id,
            {
                "run_id": run.run_id,
                "state": run.state,
                "epochs": run.config["epochs"],
                "completed_epochs": run.completed_epochs,
            },
        )

    def handle_request(self, data: Any) -> dict[str, Any]:
        request_id = data.get("request_id") if isinstance(data, dict) else None
        try:
            request = Request.from_dict(data)
            if request.method == METHOD_HEALTH:
                if request.payload:
                    raise ProtocolError(
                        "invalid_request", "health payload must be empty"
                    )
                return success_response(
                    request.request_id, {"service": "snake-lab"}
                )
            if request.method == METHOD_SIMULATION_SUBMIT:
                return self._submit(request)
            if request.method == METHOD_SIMULATION_STATUS:
                return self._status(request)
            raise ProtocolError(
                "unknown_method", f"Unknown method: {request.method}"
            )
        except ProtocolError as error:
            return error_response(request_id, error.code, str(error))

    def _execute_simulation(self, run: SimulationRun) -> None:
        """Execute the simulation workload."""
        Simulator(run.config).run()
        run.completed_epochs = run.config["epochs"]

    def _write_results(self, run: SimulationRun) -> None:
        """Stub result persistence until MariaDB integration is added."""
        self.log.info(
            f"Simulation {run.run_id} completed {run.completed_epochs} epochs"
        )

    def _worker_loop(self) -> None:
        while True:
            run = self._run_queue.get()
            if run is None:
                return
            if self._stop_event.is_set():
                return

            run.state = "running"
            self.log.info(f"Running simulation {run.run_id}")
            self._execute_simulation(run)
            self._write_results(run)
            run.state = "completed"

    def run(self) -> None:
        self._socket.bind(self.endpoint)
        self._worker.start()
        print(f"SnakeLab server listening on {self.endpoint}", flush=True)
        self.log.info(f"SnakeLab server listening on {self.endpoint}")

        try:
            while not self._stop_event.is_set():
                if self._socket.poll(timeout=500) == 0:
                    continue
                response = self.handle_request(self._socket.recv_json())
                self._socket.send_json(response)
        finally:
            self._stop_event.set()
            self._run_queue.put(None)
            self._worker.join()
            self._socket.close()
            self._context.term()
            self.log.shutdown()


def main() -> None:
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
