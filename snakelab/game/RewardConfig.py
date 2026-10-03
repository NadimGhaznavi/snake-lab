"""Rewards applied by the game rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Rewards applied by the game rules."""

    food: float
    wall: float
    snake: float
    max_moves: float
    empty: float
    closer_to_food: float
    further_from_food: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} reward must be numeric")
            object.__setattr__(self, name, float(value))
