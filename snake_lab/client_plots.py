"""Bounded plots of the live episode stream; no history or persistence."""

from collections import Counter, deque
from typing import Any

from rich.segment import Segment
from textual.app import ComposeResult
from textual.containers import Grid
from textual.strip import Strip
from textual_hires_canvas import Canvas
from textual_plot.plot_widget import Legend
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane
from textual_plot import HiResMode, LegendLocation, PlotWidget


class StyledCanvas(Canvas):
    """Supply styles for empty canvas strips in monochrome terminals.

    textual-hires-canvas 0.14.0 emits an unstyled empty strip before resize;
    Textual's monochrome filter expects every segment to have a Rich style.
    """

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        return Strip(
            [Segment(segment.text, segment.style or self.rich_style, segment.control)
             for segment in strip], strip.cell_length
        )


class LivePlotWidget(PlotWidget):
    def compose(self) -> ComposeResult:
        with Grid():
            for name in ("margin-top", "margin-left", "plot", "margin-bottom"):
                yield StyledCanvas(1, 1, id=name)
        yield Legend(id="legend")


class LivePlots(Widget):
    MAX_POINTS = 500

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.episodes: deque[tuple[int, float, int, float | None]] = deque(maxlen=self.MAX_POINTS)
        # Aggregate the whole observed run, independently of the rolling plots.
        self.score_counts: Counter[float] = Counter()
        self._dirty = False

    def compose(self) -> ComposeResult:
        with TabbedContent():
            for title, name in (("Game Score", "scores"), ("Highscores", "records"),
                                ("Loss", "losses"), ("Score Distribution", "distribution")):
                with TabPane(title, id=f"tab-{name}"):
                    yield LivePlotWidget(id=f"plot-{name}")

    def on_mount(self) -> None:
        for name, label in (("scores", "Score"), ("records", "Highscore"), ("losses", "Loss")):
            plot = self.query_one(f"#plot-{name}", PlotWidget)
            plot.set_xlabel("Episode")
            plot.set_ylabel(label)
        distribution = self.query_one("#plot-distribution", PlotWidget)
        distribution.set_xlabel("Score")
        distribution.set_ylabel("Episodes")
        distribution.set_ylimits(0, None)
        self.set_interval(0.5, self.redraw)

    def add_episode(self, episode: dict[str, Any], high_score: int) -> None:
        number = episode.get("episode")
        score = episode.get("score")
        if not isinstance(number, int) or not isinstance(score, (int, float)):
            return
        if self.episodes and number <= self.episodes[-1][0]:
            return
        self.episodes.append((number, score, high_score, episode.get("loss")))
        self.score_counts[score] += 1
        self._dirty = True

    def reset(self) -> None:
        self.episodes.clear()
        self.score_counts.clear()
        for plot in self.query(PlotWidget):
            plot.clear()
        self._dirty = False

    def redraw(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        rows = list(self.episodes)
        for name, column in (("scores", 1), ("records", 2), ("losses", 3)):
            plot = self.query_one(f"#plot-{name}", PlotWidget)
            plot.clear()
            points = [(row[0], row[column]) for row in rows if row[column] is not None]
            if points:
                plot.plot(x=[p[0] for p in points], y=[p[1] for p in points],
                          hires_mode=HiResMode.BRAILLE, line_style="green",
                          label="Current" if name == "scores" else None)
            if name == "scores" and len(points) >= 20:
                averages = [sum(p[1] for p in points[i-19:i+1]) / 20
                            for i in range(19, len(points))]
                plot.plot(x=[p[0] for p in points[19:]], y=averages,
                          hires_mode=HiResMode.BRAILLE, line_style="red", label="Average (20)")
            if name == "scores":
                plot.show_legend(location=LegendLocation.TOPLEFT)
        distribution = self.query_one("#plot-distribution", PlotWidget)
        distribution.clear()
        if self.score_counts:
            scores = sorted(self.score_counts)
            distribution.bar(
                x=scores, y=[self.score_counts[score] for score in scores],
                width=0.8, bar_style="green", hires_mode=HiResMode.HALFBLOCK,
            )
