"""One integer coordinate on the board."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    """One integer coordinate on the board."""

    x: int
    y: int
