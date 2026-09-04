"""Minimal Textual client for live SnakeLab telemetry."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, RichLog

from constants.DSnakeLab import DSnakeLab
from snake_lab.board import SnakeBoard
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


class SnakeLabViewer(App[None]):
    """Display the current SnakeLab run without controlling its hot loop."""

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
        height: 15;
        border: round #2aa5ce;
        border-title-color: #42bbc4;
        padding: 0 1;
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
        telemetry_port: int = DSnakeLab.TELEMETRY_PORT,
    ) -> None:
        super().__init__()
        self._host = host
        self._telemetry_port = telemetry_port
        self._subscriber: TelemetrySubscriber | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._sequences: dict[str, int] = {}
        self._active_run: str | None = None
        self._high_score = 0

    def compose(self) -> ComposeResult:
        yield Label("SnakeLab Live Telemetry", id="title")
        with Horizontal(id="main"):
            with Vertical(id="board-panel"):
                yield SnakeBoard(id="board")
            with Vertical(id="sidebar"):
                with Vertical(id="status-panel"):
                    yield Label("Connection: starting", id="connection")
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
        self.query_one("#event-log").border_title = "Events"
        self._subscriber = TelemetrySubscriber(
            host=self._host,
            port=self._telemetry_port,
        )
        self.query_one("#connection", Label).update(
            f"Connection: {self._host}:{self._telemetry_port}"
        )
        self._listen_task = asyncio.create_task(
            self._listen(), name="viewer-telemetry"
        )
        self._write_event("Listening for SnakeLab telemetry")

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

    async def on_unmount(self) -> None:
        task = self._listen_task
        self._listen_task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._subscriber is not None:
            self._subscriber.close()
            self._subscriber = None

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
                self._write_event(
                    f"Run {envelope.run_id[:12]} queued"
                )
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
        if self._high_score > previous_high_score:
            self._write_event(
                f"[green]New high score {self._high_score} "
                f"at episode {episode.get('episode')}[/green]"
            )

    def _show_run(self, payload: dict[str, Any]) -> None:
        state = str(payload.get("state", "unknown"))
        self.query_one("#run-state", Label).update(f"State: {state}")
        runtime = payload.get("runtime")
        detail = f" ({runtime})" if runtime else ""
        self._write_event(f"Run {state}{detail}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View live SnakeLab telemetry"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--telemetry-port", type=int, default=DSnakeLab.TELEMETRY_PORT
    )
    args = parser.parse_args()
    SnakeLabViewer(
        host=args.host,
        telemetry_port=args.telemetry_port,
    ).run()


if __name__ == "__main__":
    main()
