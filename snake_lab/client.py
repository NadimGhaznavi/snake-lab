"""Textual client for SnakeLab simulation submission and live telemetry."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Coroutine
from pathlib import Path
from datetime import datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.theme import Theme
from textual.screen import ModalScreen
from textual.validation import Integer
from textual.widgets import Button, Checkbox, Input, Label, RichLog, Select
from snake_lab.client_plots import LivePlots
from snake_lab.client_config import ConfigurationReader, TUNED_FIELDS

from constants.DSnakeLab import DSnakeLab
from snake_lab.board import SnakeBoard
from snake_lab.control_client import AsyncLabClient, load_config
from snake_lab.runtime_control import MAX_MOVE_DELAY_MS, MOVE_DELAY_STEP_MS
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


class ConfigurationReceived(Message):
    def __init__(self, run_id: str, values: dict[str, Any] | None) -> None:
        super().__init__()
        self.run_id = run_id
        self.values = values


class ConfigFileScreen(ModalScreen[str | None]):
    """Prompt for a JSON configuration file on the client host."""

    BINDINGS = [
        ("escape", "dismiss_config", "Back"),
        ("q", "dismiss_config", "Back"),
    ]
    CSS = """
    ConfigFileScreen {
        align: center middle;
    }
    #config-dialog {
        width: 76;
        max-width: 90%;
        height: 11;
        padding: 1 2;
        background: #080c10;
        border: round #2aa5ce;
    }
    #config-prompt {
        height: 1;
    }
    #config-path {
        width: 100%;
    }
    #config-actions {
        height: 1;
    }
    #config-actions Button {
        width: 1fr;
        min-width: 0;
    }
    """

    def __init__(self, initial_path: str) -> None:
        super().__init__()
        self._initial_path = initial_path

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog"):
            yield Label("JSON configuration file", id="config-prompt")
            yield Input(
                value=self._initial_path,
                placeholder="/path/to/config.json",
                id="config-path",
            )
            with Horizontal(id="config-actions"):
                yield Button("Back", id="config-cancel", compact=True)
                yield Button(
                    "Submit",
                    variant="primary",
                    id="config-submit",
                    compact=True,
                )

    def on_mount(self) -> None:
        self.query_one("#config-path", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._submit_path()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-submit":
            self._submit_path()
        elif event.button.id == "config-cancel":
            self.dismiss(None)

    def _submit_path(self) -> None:
        path = self.query_one("#config-path", Input).value.strip()
        if path:
            self.dismiss(path)

    def action_dismiss_config(self) -> None:
        self.dismiss(None)


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


class SnakeLabClient(App[None]):
    """Submit simulations, display telemetry, and expose human controls."""

    TITLE = "SnakeLab Live"
    BINDINGS = [("q", "quit", "Quit")]
    CSS_PATH = "client.tcss"

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        control_port: int = DSnakeLab.PORT,
        telemetry_port: int = DSnakeLab.TELEMETRY_PORT,
        control_client: AsyncLabClient | None = None,
        configuration_reader: ConfigurationReader | None = None,
    ) -> None:
        super().__init__()
        self._configuration_reader = configuration_reader or ConfigurationReader()
        self._config_task: asyncio.Task[Any] | None = None
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
        self._display_every = 1
        self._frames_until_display = 0
        self._show_only_highscores = False
        self._best_frame: FrameTelemetry | None = None
        self._reported_missing_high_score = 0
        self._control_busy = False
        self._high_score = 0
        self._last_config_path = "examples/sample-config.json"

    def compose(self) -> ComposeResult:
        delay_options = [("Off — full speed", 0)] + [
            (f"{delay} ms", delay)
            for delay in range(
                MOVE_DELAY_STEP_MS,
                MAX_MOVE_DELAY_MS + 1,
                MOVE_DELAY_STEP_MS,
            )
        ]
        yield Label("SnakeLab Live Telemetry", id="title")
        with VerticalScroll(id="main"):
            with Horizontal(id="top-row"):
                with Vertical(id="left-column"):
                    with VerticalScroll(id="configuration-panel"):
                        yield Label("Configuration unavailable for this run", id="configuration-values", markup=False)
                    with Vertical(id="controls-panel"):
                        yield Button("Submit config…", id="submit-config", compact=True)
                        with Horizontal(id="control-buttons"):
                            yield Button("Pause", id="pause-resume", disabled=True, compact=True)
                            yield Button("Cancel", id="cancel-run", variant="error", disabled=True, compact=True)
                        yield Label("Move delay")
                        yield Select[int](delay_options, value=0, allow_blank=False,
                                          id="move-delay", disabled=True, compact=True)
                        yield Label("Live telemetry", id="diagnostic-mode")
                        yield Checkbox("Show only highscores", id="show-only-highscores", compact=True)
                        with Horizontal(id="frame-display"):
                            yield Label("Display every ")
                            yield Input(value="1", type="integer", validators=[Integer(minimum=1)],
                                        valid_empty=False, id="display-every")
                            yield Label(" frames")
                with Vertical(id="board-panel"):
                    yield SnakeBoard(id="board")
                with Vertical(id="right-column"):
                    with Vertical(id="status-panel"):
                        yield Label(f"Server: {self._host}", id="connection", markup=False)
                        yield Label("Run: waiting", id="run")
                        yield Label("State: idle", id="run-state")
                        yield Label("Progress: 0/0", id="progress")
                        yield Label("Episode: 0  Step: 0", id="episode")
                        yield Label("Score: 0  High: 0", id="score")
                        yield Label("Epsilon: --", id="epsilon")
                        yield Label("Loss: --", id="loss")
                        yield Label("Reward: --", id="reward")
                        yield Label("Outcome: --", id="outcome")
                        yield Label("Total steps: 0", id="total-steps")
                        yield Label("Epsilon injections: 0", id="injections")
                    with Vertical(id="highscores-panel"):
                        yield Label("Episode  Score  Received", classes="table-heading")
                        yield RichLog(id="highscores", max_lines=200, wrap=False)
            yield LivePlots(id="plots")
            yield RichLog(id="event-log", max_lines=300, wrap=True, markup=True)

    async def on_mount(self) -> None:
        self.register_theme(Theme(
            name="snake-lab", primary="#88C0D0", secondary="#1f6a83",
            accent="#B48EAD", foreground="#31b8e6", background="#000000",
            success="#A3BE8C", warning="#EBCB8B", error="#BF616A",
            surface="#111111", panel="#000000", dark=True,
        ))
        self.theme = "snake-lab"
        self.query_one("#board-panel").border_title = "Snake"
        self.query_one("#status-panel").border_title = "Runtime Values"
        self.query_one("#configuration-panel").border_title = "Configuration"
        self.query_one("#highscores-panel").border_title = "Highscores"
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
            self._listen(), name="client-telemetry"
        )
        self._spawn(self._discover_active_run(), "client-active-run")
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
        if run_id != self._active_run:
            if self._config_task is not None:
                self._config_task.cancel()
            self._config_task = asyncio.create_task(self._load_configuration(run_id))
            self._tasks.add(self._config_task)
            self._config_task.add_done_callback(self._tasks.discard)
            self.query_one("#plots", LivePlots).reset()
            self.query_one("#highscores", RichLog).clear()
            self.query_one("#configuration-values", Label).update("Configuration unavailable for this run")
            for selector, value in (("reward", "Reward: --"), ("outcome", "Outcome: --"),
                                    ("epsilon", "Epsilon: --"), ("loss", "Loss: --"),
                                    ("total-steps", "Total steps: 0"), ("injections", "Epsilon injections: 0")):
                self.query_one(f"#{selector}", Label).update(value)
            self._frames_until_display = 0
            self._high_score = 0
            self._best_frame = None
            self._reported_missing_high_score = 0
            if self._show_only_highscores:
                self._clear_board()
        self._active_run = run_id
        self.query_one("#run", Label).update(f"Run: {run_id[:12]}")

    async def _load_configuration(self, run_id: str) -> None:
        try:
            values = await asyncio.to_thread(self._configuration_reader.read, run_id)
        except Exception:
            # Avoid exposing credentials or connection details in the dashboard.
            values = None
        self.post_message(ConfigurationReceived(run_id, values))

    def on_configuration_received(self, message: ConfigurationReceived) -> None:
        if message.run_id != self._active_run:
            return
        text = "Configuration unavailable for this run"
        if message.values is not None:
            text = "\n".join(
                f"{label}: {message.values.get(field, '--')}" for field, label in TUNED_FIELDS
            )
        else:
            self._write_event("Configuration unavailable: check database access and --db-credentials.")
        self.query_one("#configuration-values", Label).update(text)

    def on_telemetry_error(self, message: TelemetryError) -> None:
        self._write_event(f"[red]Telemetry error: {message.error}[/red]")

    def _clear_board(self) -> None:
        self.query_one("#board", SnakeBoard).snapshot = None
        self.query_one("#board-panel").border_title = "Snake"
        self.query_one("#board-panel").border_subtitle = "Waiting for a new highscore"

    def _show_frame(self, frame: FrameTelemetry) -> None:
        if self._best_frame is None or frame.board.score > self._best_frame.board.score:
            self._best_frame = frame
        if self._show_only_highscores:
            self._refresh_highscore_board()
            return
        if self._frames_until_display:
            self._frames_until_display -= 1
            return
        self._frames_until_display = self._display_every - 1
        self._render_frame(frame)

    def _refresh_highscore_board(self) -> None:
        if not self._show_only_highscores:
            return
        frame = self._best_frame
        board = self.query_one("#board", SnakeBoard)
        if (
            frame is not None
            and frame.board.score > 0
            and frame.board.score >= self._high_score
            and (board.snapshot is None or frame.board.score > board.snapshot.score)
        ):
            self._render_frame(frame)
        score = board.snapshot.score if board.snapshot is not None else "--"
        self.query_one("#score", Label).update(
            f"Score: {score}  High: {self._high_score}"
        )
        if self._high_score > 0 and (
            board.snapshot is None or board.snapshot.score < self._high_score
        ):
            self.query_one("#board-panel").border_subtitle = "Not Available"
            if self._high_score > self._reported_missing_high_score:
                self._reported_missing_high_score = self._high_score
                self._write_event(
                    f"[yellow]Dropped frames: no board received for "
                    f"highscore {self._high_score}.[/yellow]"
                )

    def _render_frame(self, frame: FrameTelemetry) -> None:
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
        self._show_totals(summary)
        self.query_one("#plots", LivePlots).add_episode(episode, self._high_score)
        if self._high_score > previous_high_score:
            self.query_one("#highscores", RichLog).write(
                f"{episode.get('episode', 0):7} {self._high_score:6}  {datetime.now():%H:%M:%S}"
            )
            self._write_event(
                f"[green]New high score {self._high_score} "
                f"at episode {episode.get('episode')}[/green]"
            )

    def _show_episode_values(self, episode: dict[str, Any]) -> None:
        self.query_one("#score", Label).update(
            f"Score: {episode.get('score', 0)}  High: {self._high_score}"
        )
        self._refresh_highscore_board()
        self.query_one("#reward", Label).update(f"Reward: {episode.get('reward', '--')}")
        self.query_one("#outcome", Label).update(f"Outcome: {episode.get('outcome', '--')}")
        self.query_one("#episode", Label).update(
            f"Episode: {episode.get('episode', '--')}  Step: {episode.get('steps', '--')}"
        )
        epsilon = episode.get("epsilon")
        loss = episode.get("loss")
        self.query_one("#epsilon", Label).update(
            "Epsilon: --" if epsilon is None else f"Epsilon: {epsilon:.4f}"
        )
        self.query_one("#loss", Label).update(
            "Loss: --" if loss is None else f"Loss: {loss:.6f}"
        )

    def _show_totals(self, payload: dict[str, Any]) -> None:
        for field, selector, label in (
            ("total_steps", "total-steps", "Total steps"),
            ("epsilon_injections", "injections", "Epsilon injections"),
        ):
            if field in payload:
                self.query_one(f"#{selector}", Label).update(f"{label}: {payload[field]}")

    def _show_run(
        self, payload: dict[str, Any], *, write_event: bool = True
    ) -> None:
        self._show_totals(payload)
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
            self._refresh_highscore_board()
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
        self.query_one("#submit-config", Button).disabled = (
            self._control_busy
        )
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
            else "Live telemetry"
        )
        self.query_one("#diagnostic-mode", Label).update(mode)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-config":
            self.push_screen(
                ConfigFileScreen(self._last_config_path),
                self._config_selected,
            )
        elif event.button.id == "pause-resume":
            operation = "resume" if self._run_state == "paused" else "pause"
            self._begin_control(operation)
        elif event.button.id == "cancel-run" and self._active_run is not None:
            self.push_screen(
                CancelRunScreen(self._active_run),
                self._cancel_confirmed,
            )

    def _config_selected(self, config_path: str | None) -> None:
        if config_path is None:
            return
        self._last_config_path = config_path
        self._begin_submission(config_path)

    def _begin_submission(self, config_path: str) -> None:
        if self._control_client is None or self._control_busy:
            return
        self._control_busy = True
        self._refresh_controls()
        self._spawn(
            self._send_submission(config_path),
            "client-config-submit",
        )

    async def _send_submission(self, config_path: str) -> None:
        client = self._control_client
        if client is None:
            return
        try:
            path = Path(config_path).expanduser()
            config = load_config(path)
            response = await client.submit(config)
            self.post_message(ControlResult("submit", response=response))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.post_message(ControlResult("submit", error=error))

    def _cancel_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self._begin_control("cancel")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != "show-only-highscores":
            return
        self._show_only_highscores = event.value
        self._frames_until_display = 0
        self.query_one("#frame-display").disabled = event.value
        self.query_one("#display-every", Input).disabled = event.value
        if event.value:
            self._clear_board()
            self._refresh_highscore_board()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "display-every":
            return
        if not event.value.isdecimal():
            return
        interval = int(event.value)
        if interval > 0 and interval != self._display_every:
            self._display_every = interval
            self._frames_until_display = 0

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
            f"client-control-{operation}",
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
                f"[red]Request failed: {message.error}[/red]"
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
        if message.operation == "submit":
            if not isinstance(payload, dict):
                self._write_event(
                    "[red]Submission response has an invalid payload[/red]"
                )
                self._refresh_controls()
                return
            run_id = payload.get("run_id")
            state = str(payload.get("state", "queued"))
            if self._active_run is None or self._run_state in {
                "idle",
                "completed",
                "cancelled",
                "failed",
            }:
                self._high_score = 0
                self._move_delay_ms = 0
                self._apply_run_status(payload)
            self._write_event(
                f"Submitted {self._last_config_path}: "
                f"run {str(run_id)[:12]} {state}"
            )
            self._refresh_controls()
            return
        if isinstance(payload, dict):
            self._apply_run_status(payload)
        self._write_event(f"Control accepted: {message.operation}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit, view, and control SnakeLab simulations"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--control-port", type=int, default=DSnakeLab.PORT
    )
    parser.add_argument(
        "--telemetry-port", type=int, default=DSnakeLab.TELEMETRY_PORT
    )
    parser.add_argument("--db-host", default=DSnakeLab.DB_HOST)
    parser.add_argument("--db-port", type=int, default=DSnakeLab.DB_PORT)
    parser.add_argument("--db-credentials", default=DSnakeLab.DB_CREDENTIALS_FILE)
    args = parser.parse_args()
    SnakeLabClient(
        host=args.host,
        control_port=args.control_port,
        telemetry_port=args.telemetry_port,
        configuration_reader=ConfigurationReader(
            host=args.db_host, port=args.db_port, credentials_file=args.db_credentials
        ),
    ).run()


if __name__ == "__main__":
    main()
