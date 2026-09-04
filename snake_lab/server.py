"""ZeroMQ request/reply server for SnakeLab."""

import argparse
import asyncio
import signal
import uuid
from dataclasses import dataclass
from typing import Any

import zmq
import zmq.asyncio

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
from snake_lab.simulator import EpisodeResult, SimulationState, Simulator
from utils.MyLog import MyLog


@dataclass(slots=True)
class SimulationRun:
    run_id: str
    config: dict[str, Any]
    state: str = "queued"
    completed_epochs: int = 0
    total_steps: int = 0
    high_score: int = 0
    total_reward: float = 0.0
    epsilon_injections: int = 0
    last_loss: float | None = None
    last_episode: EpisodeResult | None = None
    error: str | None = None


class SnakeLabServer:
    """Accept and execute SnakeLab simulation requests."""

    def __init__(
        self,
        address: str = "*",
        port: int = DSnakeLab.PORT,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
    ) -> None:
        self.endpoint = f"tcp://{address}:{port}"
        self._log_file = log_file
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.REP)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._stop_event = asyncio.Event()
        self._run_queue: asyncio.Queue[SimulationRun] = asyncio.Queue()
        self._runs: dict[str, SimulationRun] = {}
        self._config_template = simulation_config_template()
        self._worker_task: asyncio.Task[None] | None = None
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
        self._run_queue.put_nowait(run)
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
        result = {
            "run_id": run.run_id,
            "state": run.state,
            "epochs": run.config["epochs"],
            "completed_epochs": run.completed_epochs,
            "total_steps": run.total_steps,
            "high_score": run.high_score,
            "total_reward": run.total_reward,
            "epsilon_injections": run.epsilon_injections,
            "last_loss": run.last_loss,
            "last_episode": (
                run.last_episode.to_dict()
                if run.last_episode is not None
                else None
            ),
        }
        if run.error is not None:
            result["error"] = run.error
        return success_response(
            request.request_id,
            result,
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

    async def _execute_simulation(self, run: SimulationRun) -> None:
        """Execute the simulation workload."""
        def update_progress(
            episode: EpisodeResult, state: SimulationState
        ) -> None:
            run.completed_epochs = state.completed_epochs
            run.total_steps = state.total_steps
            run.high_score = state.high_score
            run.total_reward = state.total_reward
            run.epsilon_injections = state.total_epsilon_injections
            run.last_loss = state.last_loss
            run.last_episode = episode

        simulator = Simulator(
            run.config,
            log_file=self._log_file,
            on_episode=update_progress,
        )
        await simulator.run()

    def _write_results(self, run: SimulationRun) -> None:
        """Stub result persistence until MariaDB integration is added."""
        self.log.info(
            f"Simulation {run.run_id} completed {run.completed_epochs} epochs"
        )

    async def _worker_loop(self) -> None:
        """Execute queued simulations serially in FIFO order."""
        while True:
            run = await self._run_queue.get()
            try:
                run.state = "running"
                self.log.info(f"Running simulation {run.run_id}")
                await self._execute_simulation(run)
                self._write_results(run)
                run.state = "completed"
            except asyncio.CancelledError:
                run.state = "cancelled"
                raise
            except Exception as error:
                run.state = "failed"
                run.error = str(error)
                self.log.error(
                    f"Simulation {run.run_id} failed: {error}"
                )
            finally:
                self._run_queue.task_done()

    async def _shutdown_worker(self) -> None:
        """Cancel the owned worker and mark queued work as cancelled."""
        worker_task = self._worker_task
        self._worker_task = None
        if worker_task is not None:
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)

        while not self._run_queue.empty():
            run = self._run_queue.get_nowait()
            run.state = "cancelled"
            self._run_queue.task_done()

    async def run(self) -> None:
        """Serve requests and one serial simulation worker."""
        self._socket.bind(self.endpoint)
        self._worker_task = asyncio.create_task(
            self._worker_loop(), name="simulation-worker"
        )
        self.log.info(f"SnakeLab server listening on {self.endpoint}")

        try:
            while not self._stop_event.is_set():
                if await self._socket.poll(timeout=500) == 0:
                    continue
                request = await self._socket.recv_json()
                response = self.handle_request(request)
                await self._socket.send_json(response)
        finally:
            self._stop_event.set()
            await self._shutdown_worker()
            self._socket.close()
            self._context.term()
            self.log.shutdown()


async def amain() -> None:
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

    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, server.stop)
        except (NotImplementedError, RuntimeError):
            pass
    await server.run()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
