"""Textual client for live SnakeLab telemetry and human runtime controls."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Coroutine
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RichLog, Select

from constants.DSnakeLab import DSnakeLab
from snake_lab.board import SnakeBoard
from snake_lab.client import AsyncLabClient
from snake_lab.runtime_control import MAX_MOVE_DELAY_MS
from snake_lab.telemetry import (
    TOPIC_EPISODE,
    TOPIC_FRAME,
    TOPIC_RUN,
    FrameTelemetry,
    TelemetryEnvelope,
)
from snake_lab.telemetry_zmq import TelemetrySubscriber


class TelemetryReceived(Message):
    def __init__(self, topic: str, envelope: TelemetryEnvelope) -> None:
        super().__init__()
        self.topic = topic
        self.envelope = envelope


class TelemetryError(Message):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error


class ControlResult(Message):
    def __init__(
        self,
        operation: str,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.operation = operation
        self.response = response
        self.error = error


class CancelRunScreen(ModalScreen[bool]):
    """Require an explicit confirmation before cancelling a run."""

    BINDINGS = [
        ("escape", "dismiss_cancel", "Back"),
        ("q", "dismiss_cancel", "Back"),
    ]
    CSS = """
    CancelRunScreen {
        align: center middle;
    }
    #cancel-dialog {
        grid-size: 2;
        grid-rows: 1fr 3;
        grid-columns: 1fr 1fr;
        width: 62;
        height: 10;
        padding: 1 2;
        background: #080c10;
        border: round #d75f00;
    }
    #cancel-question {
        column-span: 2;
        height: 1fr;
        content-align: center middle;
        text-align: center;
    }
    #cancel-dialog Button {
        width: 1fr;
        min-width: 0;
    }
    """

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id

    def compose(self) -> ComposeResult:
        with Grid(id="cancel-dialog"):
            yield Label(
                f"Cancel simulation {self._run_id[:12]}?\n"
                "Completed episode progress will remain available.",
                id="cancel-question",
            )
            yield Button("Keep running", id="keep-running", compact=True)
            yield Button("Cancel run", variant="error", id="confirm-cancel", compact=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-cancel")

    def action_dismiss_cancel(self) -> None:
        self.dismiss(False)


class SnakeLabViewer(App[None]):
    """Display live telemetry and operate human-only runtime controls."""

    TITLE = "SnakeLab Live"
    BINDINGS = [("q", "quit", "Quit")]
    CSS = """
    Screen {
        background: black;
        color: #31b8e6;
    }
    #title {
        height: 3;
        border: round #2aa5ce;
        color: #5fc442;
        text-style: bold;
        padding: 0 1;
    }
    #main {
        height: 1fr;
    }
    #board-panel {
        width: 2fr;
        height: 100%;
        border: round #2aa5ce;
        border-title-color: #42bbc4;
        border-subtitle-color: #42bbc4;
        padding: 0 1;
    }
    #sidebar {
        width: 42;
        height: 100%;
    }
    #status-panel {
        height: 10;
        border: round #2aa5ce;
        border-title-color: #42bbc4;
        padding: 0 1;
    }
    #controls-panel {
        height: 10;
        border: round #2aa5ce;
        border-title-color: #42bbc4;
        padding: 0 1;
    }
    #control-buttons {
        height: 1;
    }
    #control-buttons Button {
        width: 1fr;
        min-width: 0;
    }
    #move-delay {
        width: 100%;
    }
    #diagnostic-mode {
        height: 1;
        color: #9a9a9a;
    }
    #event-log {
        height: 1fr;
        border: round #2aa5ce;
        border-title-color: #42bbc4;
        scrollbar-color: #2aa5ce;
    }
    SnakeBoard {
        width: 100%;
        height: 100%;
        background: black;
    }
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        control_port: int = DSnakeLab.PORT,
        telemetry_port: int = DSnakeLab.TELEMETRY_PORT,
        control_client: AsyncLabClient | None = None,
    ) -> None:
        super().__init__()
        self._host = host
        self._control_port = control_port
        self._telemetry_port = telemetry_port
        self._subscriber: TelemetrySubscriber | None = None
        self._control_client = control_client
        self._listen_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._sequences: dict[str, int] = {}
        self._active_run: str | None = None
        self._run_state = "idle"
        self._move_delay_ms = 0
        self._control_busy = False
        self._high_score = 0

    def compose(self) -> ComposeResult:
        delay_options = [("Off — full speed", 0)] + [
            (f"{delay} ms", delay)
            for delay in range(50, MAX_MOVE_DELAY_MS + 1, 50)
        ]
        yield Label("SnakeLab Live Telemetry", id="title")
        with Horizontal(id="main"):
            with Vertical(id="board-panel"):
                yield SnakeBoard(id="board")
            with Vertical(id="sidebar"):
                with Vertical(id="controls-panel"):
                    with Horizontal(id="control-buttons"):
                        yield Button(
                            "Pause", id="pause-resume", disabled=True, compact=True
                        )
                        yield Button(
                            "Cancel",
                            id="cancel-run",
                            variant="error",
                            disabled=True,
                            compact=True
                        )
                    yield Label("Move delay")
                    yield Select[int](
                        delay_options,
                        value=0,
                        allow_blank=False,
                        id="move-delay",
                        disabled=True,
                    )
                    yield Label(
                        "Sampled telemetry", id="diagnostic-mode"
                    )
                with Vertical(id="status-panel"):
                    yield Label(
                        f"Server: {self._host} "
                        f"({self._control_port}/{self._telemetry_port})",
                        id="connection",
                    )
                    yield Label("Run: waiting", id="run")
                    yield Label("State: idle", id="run-state")
                    yield Label("Progress: 0/0", id="progress")
                    yield Label("Episode: 0  Step: 0", id="episode")
                    yield Label("Score: 0  High: 0", id="score")
                    yield Label("Epsilon: --", id="epsilon")
                    yield Label("Loss: --", id="loss")
                yield RichLog(id="event-log", wrap=True, markup=True)

    async def on_mount(self) -> None:
        self.query_one("#board-panel").border_title = "Snake"
        self.query_one("#status-panel").border_title = "Run"
        self.query_one("#controls-panel").border_title = "Controls"
        self.query_one("#event-log").border_title = "Events"
        self._subscriber = TelemetrySubscriber(
            host=self._host,
            port=self._telemetry_port,
        )
        if self._control_client is None:
            self._control_client = AsyncLabClient(
                host=self._host, port=self._control_port
            )
        self._listen_task = asyncio.create_task(
            self._listen(), name="viewer-telemetry"
        )
        self._spawn(self._discover_active_run(), "viewer-active-run")
        self._write_event("Listening for SnakeLab telemetry")

    def _spawn(self, coroutine: Coroutine[Any, Any, Any], name: str) -> None:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _listen(self) -> None:
        if self._subscriber is None:
            return
        while True:
            try:
                topic, envelope = await self._subscriber.receive()
                self.post_message(TelemetryReceived(topic, envelope))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.post_message(TelemetryError(error))

    async def _discover_active_run(self) -> None:
        client = self._control_client
        if client is None:
            return
        try:
            response = await client.active()
            self.post_message(ControlResult("discover", response=response))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.post_message(ControlResult("discover", error=error))

    async def on_unmount(self) -> None:
        tasks = list(self._tasks)
        self._tasks.clear()
        if self._listen_task is not None:
            tasks.append(self._listen_task)
            self._listen_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._subscriber is not None:
            self._subscriber.close()
            self._subscriber = None
        if self._control_client is not None:
            self._control_client.close()
            self._control_client = None

    def _write_event(self, message: str) -> None:
        self.query_one("#event-log", RichLog).write(message)

    def _check_sequence(self, topic: str, sequence: int) -> None:
        previous = self._sequences.get(topic)
        self._sequences[topic] = sequence
        if previous is not None and sequence != previous + 1:
            self._write_event(
                f"[yellow]Telemetry gap on {topic}: "
                f"{previous} → {sequence}[/yellow]"
            )

    def on_telemetry_received(self, message: TelemetryReceived) -> None:
        topic = message.topic
        envelope = message.envelope
        self._check_sequence(topic, envelope.sequence)

        if topic == TOPIC_FRAME:
            self._activate_run(envelope.run_id)
            self._show_frame(FrameTelemetry.from_dict(envelope.payload))
        elif topic == TOPIC_EPISODE:
            self._activate_run(envelope.run_id)
            self._show_episode(envelope.payload)
        elif topic == TOPIC_RUN:
            state = envelope.payload.get("state")
            if state == "queued" and self._active_run not in (
                None,
                envelope.run_id,
            ):
                self._write_event(f"Run {envelope.run_id[:12]} queued")
                return
            if state == "running" or self._active_run is None:
                self._activate_run(envelope.run_id)
            if envelope.run_id == self._active_run:
                self._show_run(envelope.payload)

    def _activate_run(self, run_id: str) -> None:
        self._active_run = run_id
        self.query_one("#run", Label).update(f"Run: {run_id[:12]}")

    def on_telemetry_error(self, message: TelemetryError) -> None:
        self._write_event(f"[red]Telemetry error: {message.error}[/red]")

    def _show_frame(self, frame: FrameTelemetry) -> None:
        self.query_one("#board", SnakeBoard).apply_snapshot(frame.board)
        self.query_one("#episode", Label).update(
            f"Episode: {frame.episode}  Step: {frame.step}"
        )
        self.query_one("#score", Label).update(
            f"Score: {frame.board.score}  High: {self._high_score}"
        )
        self.query_one("#board-panel").border_title = (
            f"Snake — Episode {frame.episode}"
        )
        self.query_one("#board-panel").border_subtitle = (
            f"Score {frame.board.score}"
        )

    def _show_episode(self, payload: dict[str, Any]) -> None:
        episode = payload.get("episode", {})
        summary = payload.get("summary", {})
        completed = summary.get("completed_epochs", 0)
        total = summary.get("epochs", 0)
        previous_high_score = self._high_score
        self._high_score = int(summary.get("high_score", self._high_score))
        self.query_one("#progress", Label).update(
            f"Progress: {completed}/{total}"
        )
        self._show_episode_values(episode)
        if self._high_score > previous_high_score:
            self._write_event(
                f"[green]New high score {self._high_score} "
                f"at episode {episode.get('episode')}[/green]"
            )

    def _show_episode_values(self, episode: dict[str, Any]) -> None:
        self.query_one("#score", Label).update(
            f"Score: {episode.get('score', 0)}  High: {self._high_score}"
        )
        epsilon = episode.get("epsilon")
        loss = episode.get("loss")
        self.query_one("#epsilon", Label).update(
            "Epsilon: --" if epsilon is None else f"Epsilon: {epsilon:.4f}"
        )
        self.query_one("#loss", Label).update(
            "Loss: --" if loss is None else f"Loss: {loss:.6f}"
        )

    def _show_run(
        self, payload: dict[str, Any], *, write_event: bool = True
    ) -> None:
        previous_state = self._run_state
        self._run_state = str(payload.get("state", "unknown"))
        self._move_delay_ms = int(
            payload.get("move_delay_ms", self._move_delay_ms)
        )
        self.query_one("#run-state", Label).update(
            f"State: {self._run_state}"
        )
        if "completed_epochs" in payload:
            self.query_one("#progress", Label).update(
                f"Progress: {payload['completed_epochs']}/"
                f"{payload.get('epochs', 0)}"
            )
        if "high_score" in payload:
            self._high_score = int(payload["high_score"])
        delay_select = self.query_one("#move-delay", Select)
        if delay_select.value != self._move_delay_ms:
            delay_select.value = self._move_delay_ms
        self._refresh_controls()

        runtime = payload.get("runtime")
        detail = f" ({runtime})" if runtime else ""
        if write_event and (self._run_state != previous_state or runtime):
            self._write_event(f"Run {self._run_state}{detail}")

    def _apply_run_status(self, payload: dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run status is missing run_id")
        self._activate_run(run_id)
        self._show_run(payload, write_event=False)
        episode = payload.get("last_episode")
        if isinstance(episode, dict):
            self._show_episode_values(episode)

    def _refresh_controls(self) -> None:
        interactive = self._run_state in {"queued", "running", "paused"}
        pause_enabled = self._run_state in {"running", "paused"}
        pause_button = self.query_one("#pause-resume", Button)
        pause_button.label = (
            "Resume" if self._run_state == "paused" else "Pause"
        )
        pause_button.disabled = self._control_busy or not pause_enabled
        self.query_one("#cancel-run", Button).disabled = (
            self._control_busy or not interactive
        )
        self.query_one("#move-delay", Select).disabled = (
            self._control_busy or not interactive
        )
        mode = (
            "Every move — diagnostic mode"
            if self._move_delay_ms > 0
            else "Sampled telemetry"
        )
        self.query_one("#diagnostic-mode", Label).update(mode)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pause-resume":
            operation = "resume" if self._run_state == "paused" else "pause"
            self._begin_control(operation)
        elif event.button.id == "cancel-run" and self._active_run is not None:
            self.push_screen(
                CancelRunScreen(self._active_run),
                self._cancel_confirmed,
            )

    def _cancel_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self._begin_control("cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.control.id != "move-delay":
            return
        if type(event.value) is int and event.value != self._move_delay_ms:
            self._begin_control("delay", event.value)

    def _begin_control(
        self, operation: str, move_delay_ms: int | None = None
    ) -> None:
        if (
            self._active_run is None
            or self._control_client is None
            or self._control_busy
        ):
            return
        self._control_busy = True
        self._refresh_controls()
        self._spawn(
            self._send_control(operation, move_delay_ms),
            f"viewer-control-{operation}",
        )

    async def _send_control(
        self, operation: str, move_delay_ms: int | None
    ) -> None:
        client = self._control_client
        run_id = self._active_run
        if client is None or run_id is None:
            return
        try:
            if operation == "pause":
                response = await client.pause(run_id)
            elif operation == "resume":
                response = await client.resume(run_id)
            elif operation == "cancel":
                response = await client.cancel(run_id)
            elif operation == "delay" and move_delay_ms is not None:
                response = await client.set_move_delay(
                    run_id, move_delay_ms
                )
            else:
                raise ValueError(f"unknown control operation: {operation}")
            self.post_message(ControlResult(operation, response=response))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.post_message(ControlResult(operation, error=error))

    def on_control_result(self, message: ControlResult) -> None:
        if message.operation != "discover":
            self._control_busy = False
        if message.error is not None:
            self._write_event(
                f"[red]Control request failed: {message.error}[/red]"
            )
            self._refresh_controls()
            return
        response = message.response
        if response is None:
            return
        if response.get("status") != "ok":
            error = response.get("error", {})
            self._write_event(
                f"[red]{error.get('message', 'Control request failed')}[/red]"
            )
            self._refresh_controls()
            return

        payload = response.get("payload", {})
        if message.operation == "discover":
            run = payload.get("run")
            if isinstance(run, dict):
                self._apply_run_status(run)
            return
        if isinstance(payload, dict):
            self._apply_run_status(payload)
        self._write_event(f"Control accepted: {message.operation}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View and control live SnakeLab simulations"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--control-port", type=int, default=DSnakeLab.PORT
    )
    parser.add_argument(
        "--telemetry-port", type=int, default=DSnakeLab.TELEMETRY_PORT
    )
    args = parser.parse_args()
    SnakeLabViewer(
        host=args.host,
        control_port=args.control_port,
        telemetry_port=args.telemetry_port,
    ).run()


if __name__ == "__main__":
    main()
