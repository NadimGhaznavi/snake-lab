"""Cooperative, human-operated controls for a running simulation."""

from __future__ import annotations

import asyncio


MAX_MOVE_DELAY_MS = 1000
MOVE_DELAY_STEP_MS = 50


class SimulationCancelled(Exception):
    """A run was cancelled through its cooperative runtime control."""


class SimulationControl:
    """Mutable runtime controls kept outside reproducible configuration."""

    def __init__(self) -> None:
        self._paused = False
        self._cancel_requested = False
        self._move_delay_ms = 0
        self._changed = asyncio.Event()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    @property
    def move_delay_ms(self) -> int:
        return self._move_delay_ms

    @property
    def diagnostic_mode(self) -> bool:
        return self._move_delay_ms > 0

    def pause(self) -> None:
        self._paused = True
        self._changed.set()

    def resume(self) -> None:
        self._paused = False
        self._changed.set()

    def cancel(self) -> None:
        self._cancel_requested = True
        self._changed.set()

    def set_move_delay(self, move_delay_ms: int) -> None:
        if (
            type(move_delay_ms) is not int
            or not 0 <= move_delay_ms <= MAX_MOVE_DELAY_MS
            or move_delay_ms % MOVE_DELAY_STEP_MS != 0
        ):
            raise ValueError(
                "move_delay_ms must be an integer from 0 through "
                f"{MAX_MOVE_DELAY_MS} in {MOVE_DELAY_STEP_MS} ms steps"
            )
        self._move_delay_ms = move_delay_ms
        self._changed.set()

    async def checkpoint(self, *, apply_delay: bool = True) -> None:
        """Yield, wait while paused, delay if requested, or cancel."""
        while True:
            self._changed.clear()
            if self._cancel_requested:
                raise SimulationCancelled
            if self._paused:
                await self._changed.wait()
                continue

            delay = self._move_delay_ms / 1000 if apply_delay else 0
            if delay > 0:
                try:
                    await asyncio.wait_for(self._changed.wait(), delay)
                except TimeoutError:
                    return
                continue

            await asyncio.sleep(0)
            if self._cancel_requested or self._paused:
                continue
            return
