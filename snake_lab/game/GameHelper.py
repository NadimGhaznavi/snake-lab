"""Shared game mechanics helpers."""

import random

from snake_lab.game.Position import Position


def random_free_position(
    rng: random.Random,
    grid_size: tuple[int, int],
    occupied: set[Position],
) -> Position | None:
    width, height = grid_size
    free = [
        Position(x, y)
        for x in range(width)
        for y in range(height)
        if Position(x, y) not in occupied
    ]
    return rng.choice(free) if free else None
