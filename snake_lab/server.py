"""ZeroMQ request/reply server for SnakeLab."""

import argparse
import asyncio
import signal
import uuid
from dataclasses import dataclass, field
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
from snake_lab.database import (
    MariaDBSimulationStore,
    MemorySimulationStore,
    SimulationStore,
)
from snake_lab.event_protocol import EVENT_SIMULATION_ENDED
from snake_lab.events_zmq import EventsPublisher
from snake_lab.protocol import (
    METHOD_HEALTH,
    METHOD_SIMULATION_ACTIVE,
    METHOD_SIMULATION_CANCEL,
    METHOD_SIMULATION_PAUSE,
    METHOD_SIMULATION_RESUME,
    METHOD_SIMULATION_SET_MOVE_DELAY,
    METHOD_SIMULATION_STATUS,
    METHOD_SIMULATION_SUBMIT,
    ProtocolError,
    Request,
    error_response,
    success_response,
)
from snake_lab.runtime_control import (
    SimulationCancelled,
    SimulationControl,
)
from snake_lab.simulator import EpisodeResult, SimulationState, Simulator
from snake_lab.telemetry_zmq import TelemetryPublisher
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
    control: SimulationControl = field(default_factory=SimulationControl)


class SnakeLabServer:
    """Accept and execute SnakeLab simulation requests."""

    def __init__(
        self,
        address: str = "*",
        port: int = DSnakeLab.PORT,
        telemetry_port: int = DSnakeLab.TELEMETRY_PORT,
        telemetry_frame_rate: float = DSnakeLab.TELEMETRY_FRAME_RATE,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        store: SimulationStore | None = None,
        events_port: int = DSnakeLab.EVENTS_PORT,
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
        self.store = store or MemorySimulationStore()
        self._worker_task: asyncio.Task[None] | None = None
        self.telemetry = TelemetryPublisher(
            context=self._context,
            address=address,
            port=telemetry_port,
            frame_rate=telemetry_frame_rate,
        )
        self.events = EventsPublisher(
            context=self._context,
            address=address,
            port=events_port,
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
        self.store.create_run(run.run_id, config, DSnakeLab.VERSION)
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
        self._publish_run(run)
        self.log.info(
            f"Queued simulation {run.run_id}: {config['epochs']} epochs"
        )
        return response

    def _status(self, request: Request) -> dict[str, Any]:
        run = self._requested_run(request, {"run_id"})
        return success_response(request.request_id, self._run_status(run))

    def _requested_run(
        self, request: Request, expected_fields: set[str]
    ) -> SimulationRun:
        if set(request.payload) != expected_fields:
            raise ProtocolError(
                "invalid_request",
                "request payload fields do not match the protocol",
            )
        run_id = request.payload["run_id"]
        if not isinstance(run_id, str) or not run_id:
            raise ProtocolError(
                "invalid_request", "run_id must be a non-empty string"
            )
        if run_id not in self._runs:
            raise ProtocolError("run_not_found", f"Unknown run: {run_id}")
        return self._runs[run_id]

    def _active(self, request: Request) -> dict[str, Any]:
        if request.payload:
            raise ProtocolError(
                "invalid_request", "active payload must be empty"
            )
        active = next(
            (
                run
                for run in self._runs.values()
                if run.state in {"running", "paused", "cancelling"}
            ),
            None,
        )
        if active is None:
            active = next(
                (
                    run
                    for run in self._runs.values()
                    if run.state == "queued"
                ),
                None,
            )
        return success_response(
            request.request_id,
            {"run": self._run_status(active) if active is not None else None},
        )

    def _pause(self, request: Request) -> dict[str, Any]:
        run = self._requested_run(request, {"run_id"})
        if run.state == "running":
            run.control.pause()
            run.state = "paused"
            self.store.set_status(run.run_id, run.state)
            self.log.info(f"Paused simulation {run.run_id}")
            self._publish_run(run)
        elif run.state != "paused":
            raise ProtocolError(
                "invalid_run_state",
                f"Cannot pause a simulation in state {run.state}",
            )
        return success_response(request.request_id, self._run_status(run))

    def _resume(self, request: Request) -> dict[str, Any]:
        run = self._requested_run(request, {"run_id"})
        if run.state == "paused":
            run.control.resume()
            run.state = "running"
            self.store.set_status(run.run_id, run.state)
            self.log.info(f"Resumed simulation {run.run_id}")
            self._publish_run(run)
        elif run.state != "running":
            raise ProtocolError(
                "invalid_run_state",
                f"Cannot resume a simulation in state {run.state}",
            )
        return success_response(request.request_id, self._run_status(run))

    def _cancel(self, request: Request) -> dict[str, Any]:
        run = self._requested_run(request, {"run_id"})
        if run.state == "queued":
            run.control.cancel()
            run.state = "cancelled"
            self._finish_run(run)
            self.log.info(f"Cancelled queued simulation {run.run_id}")
            self._publish_run(run)
        elif run.state in {"running", "paused"}:
            run.control.cancel()
            run.state = "cancelling"
            self.store.set_status(run.run_id, run.state)
            self.log.info(f"Cancelling simulation {run.run_id}")
            self._publish_run(run)
        elif run.state not in {"cancelling", "cancelled"}:
            raise ProtocolError(
                "invalid_run_state",
                f"Cannot cancel a simulation in state {run.state}",
            )
        return success_response(request.request_id, self._run_status(run))

    def _set_move_delay(self, request: Request) -> dict[str, Any]:
        run = self._requested_run(
            request, {"run_id", "move_delay_ms"}
        )
        if run.state not in {"queued", "running", "paused"}:
            raise ProtocolError(
                "invalid_run_state",
                "Move delay can only be changed for a queued or active run",
            )
        move_delay_ms = request.payload["move_delay_ms"]
        try:
            run.control.set_move_delay(move_delay_ms)
        except ValueError as error:
            raise ProtocolError("invalid_request", str(error)) from error
        self.log.info(
            f"Simulation {run.run_id} move delay set to "
            f"{move_delay_ms} ms"
        )
        self._publish_run(run)
        return success_response(request.request_id, self._run_status(run))

    def _run_status(self, run: SimulationRun) -> dict[str, Any]:
        result = {
            "run_id": run.run_id,
            "state": run.state,
            **self._run_summary(run),
            "last_episode": (
                run.last_episode.to_dict()
                if run.last_episode is not None
                else None
            ),
        }
        if run.error is not None:
            result["error"] = run.error
        return result

    def _publish_run(self, run: SimulationRun, **details: Any) -> None:
        self.telemetry.offer_run(
            run.run_id,
            {"state": run.state, **self._run_summary(run), **details},
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
            if request.method == METHOD_SIMULATION_ACTIVE:
                return self._active(request)
            if request.method == METHOD_SIMULATION_STATUS:
                return self._status(request)
            if request.method == METHOD_SIMULATION_PAUSE:
                return self._pause(request)
            if request.method == METHOD_SIMULATION_RESUME:
                return self._resume(request)
            if request.method == METHOD_SIMULATION_CANCEL:
                return self._cancel(request)
            if request.method == METHOD_SIMULATION_SET_MOVE_DELAY:
                return self._set_move_delay(request)
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
            self.store.record_episode(
                run.run_id,
                episode,
                run.completed_epochs,
                run.high_score,
            )
            self.telemetry.offer_episode(
                run.run_id,
                {
                    "episode": episode.to_dict(),
                    "summary": state.summary(),
                },
            )

        simulator = Simulator(
            run.config,
            log_file=self._log_file,
            on_episode=update_progress,
            on_frame=lambda frame: self.telemetry.offer_frame(
                run.run_id,
                frame,
                preserve=run.control.diagnostic_mode,
            ),
            runtime_control=run.control,
            frame_enabled=lambda: self.telemetry.has_frame_subscribers,
        )
        self._publish_run(run, runtime=simulator.runtime_description)
        await simulator.run()

    def _finish_run(self, run: SimulationRun) -> None:
        """Persist a terminal result before offering its ended event."""
        self.store.finish_run(
            run.run_id,
            run.state,
            run.completed_epochs,
            run.high_score,
            run.error,
        )
        payload = {"run_id": run.run_id, "state": run.state}
        if run.error is not None:
            payload["error"] = run.error
        self.events.publish_event(EVENT_SIMULATION_ENDED, payload)

    def _write_results(self, run: SimulationRun) -> None:
        """Finalize a successfully completed persistent run."""
        self._finish_run(run)
        self.log.info(
            f"Simulation {run.run_id} completed {run.completed_epochs} epochs"
        )

    async def _worker_loop(self) -> None:
        """Execute queued simulations serially in FIFO order."""
        while True:
            run = await self._run_queue.get()
            try:
                if run.state == "cancelled":
                    continue
                run.state = "running"
                self.store.mark_started(run.run_id)
                self.log.info(f"Running simulation {run.run_id}")
                await self._execute_simulation(run)
                run.state = "completed"
                self._write_results(run)
                self.telemetry.offer_run(
                    run.run_id,
                    {"state": "completed", **self._run_summary(run)},
                )
            except SimulationCancelled:
                run.state = "cancelled"
                self._finish_run(run)
                self.log.info(f"Cancelled simulation {run.run_id}")
                self._publish_run(run)
            except asyncio.CancelledError:
                run.state = "cancelled"
                self._finish_run(run)
                self.telemetry.offer_run(
                    run.run_id,
                    {"state": "cancelled", **self._run_summary(run)},
                )
                raise
            except Exception as error:
                run.state = "failed"
                run.error = str(error)
                self._finish_run(run)
                self.telemetry.offer_run(
                    run.run_id,
                    {
                        "state": "failed",
                        "error": run.error,
                        **self._run_summary(run),
                    },
                )
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
            try:
                if run.state == "cancelled":
                    continue
                run.state = "cancelled"
                self._finish_run(run)
                self._publish_run(run)
            finally:
                self._run_queue.task_done()

    def _check_worker(self) -> None:
        """Fail the service if its only simulation worker has stopped."""
        if self._worker_task is None or not self._worker_task.done():
            return
        self._worker_task.result()
        raise RuntimeError("simulation worker stopped unexpectedly")

    @staticmethod
    def _run_summary(run: SimulationRun) -> dict[str, Any]:
        return {
            "epochs": run.config["epochs"],
            "completed_epochs": run.completed_epochs,
            "total_steps": run.total_steps,
            "high_score": run.high_score,
            "total_reward": run.total_reward,
            "epsilon_injections": run.epsilon_injections,
            "last_loss": run.last_loss,
            "move_delay_ms": run.control.move_delay_ms,
        }

    async def run(self) -> None:
        """Serve requests and one serial simulation worker."""
        try:
            self._socket.bind(self.endpoint)
            self.telemetry.start()
            self.events.start()
            self._worker_task = asyncio.create_task(
                self._worker_loop(), name="simulation-worker"
            )
            self.log.info(f"SnakeLab server listening on {self.endpoint}")
            self.log.info(
                f"SnakeLab telemetry publishing on {self.telemetry.endpoint}"
            )
            self.log.info(
                f"SnakeLab events publishing on {self.events.endpoint}"
            )

            while not self._stop_event.is_set():
                self._check_worker()
                self.events.check()
                self.telemetry.check()
                if await self._socket.poll(timeout=500) == 0:
                    continue
                request = await self._socket.recv_json()
                response = self.handle_request(request)
                await self._socket.send_json(response)
        finally:
            self._stop_event.set()
            try:
                await self._shutdown_worker()
            finally:
                try:
                    await self.events.close()
                finally:
                    await self.telemetry.close()
                    self._socket.close()
                    self._context.term()
                    self.store.close()
                    self.log.shutdown()


async def amain() -> None:
    parser = argparse.ArgumentParser(description="Run the SnakeLab server")
    parser.add_argument("--address", default="*")
    parser.add_argument("--port", type=int, default=DSnakeLab.PORT)
    parser.add_argument(
        "--telemetry-port", type=int, default=DSnakeLab.TELEMETRY_PORT
    )
    parser.add_argument(
        "--events-port", type=int, default=DSnakeLab.EVENTS_PORT
    )
    parser.add_argument(
        "--telemetry-frame-rate",
        type=float,
        default=DSnakeLab.TELEMETRY_FRAME_RATE,
    )
    parser.add_argument("--log-file", default=DSnakeLab.SERVER_LOG_FILE)
    parser.add_argument(
        "--ephemeral",
        action="store_true",
        help="keep simulation results in memory instead of MariaDB",
    )
    args = parser.parse_args()

    store: SimulationStore
    if args.ephemeral:
        store = MemorySimulationStore()
    else:
        store = MariaDBSimulationStore.connect()

    server = SnakeLabServer(
        address=args.address,
        port=args.port,
        telemetry_port=args.telemetry_port,
        telemetry_frame_rate=args.telemetry_frame_rate,
        events_port=args.events_port,
        log_file=args.log_file,
        store=store,
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
