"""Deterministic epsilon-greedy exploration schedule."""

from __future__ import annotations

import random

from constants.DEpsilon import DEpsilon
from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from constants.DNNet import DNetDef
from constants.DSnakeLab import DSnakeLab
from utils.MyLog import MyLog


class EpsilonAlgo:
    """Inject random actions and decay epsilon after each episode."""

    def __init__(
        self,
        *,
        rng: random.Random,
        initial: float,
        minimum: float,
        decay: float,
        cutoff: float = DEpsilon.CUTOFF,
        action_count: int = DNetDef.OUTPUT_SIZE,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        if not isinstance(rng, random.Random):
            raise TypeError("rng must be an instance of random.Random")
        initial = self._probability("initial", initial)
        minimum = self._probability("minimum", minimum)
        decay = self._probability("decay", decay)
        cutoff = self._probability("cutoff", cutoff)
        if minimum > initial:
            raise ValueError("minimum epsilon cannot exceed initial epsilon")
        if decay == 0.0:
            raise ValueError("epsilon decay must be greater than zero")
        if type(action_count) is not int or action_count <= 0:
            raise ValueError("action_count must be a positive integer")

        self._rng = rng
        self.initial = initial
        self.minimum = minimum
        self.decay = decay
        self.cutoff = cutoff
        self.action_count = action_count
        self.log = log or MyLog(
            client_id=DModule.EPSILON_ALGO,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )
        self._epsilon = self.initial
        self._episode_injections = 0
        self._total_injections = 0
        self._episodes = 0
        self._floor_logged = False
        self.log.info(
            f"Initialized epsilon schedule: initial={self.initial}, "
            f"minimum={self.minimum}, decay={self.decay}"
        )

    @staticmethod
    def _probability(name: str, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} epsilon must be numeric")
        normalized = float(value)
        if not 0.0 <= normalized <= 1.0:
            raise ValueError(f"{name} epsilon must be in the range [0, 1]")
        return normalized

    @property
    def current(self) -> float:
        return self._epsilon

    @property
    def episode_injections(self) -> int:
        return self._episode_injections

    @property
    def total_injections(self) -> int:
        return self._total_injections

    @property
    def episodes(self) -> int:
        return self._episodes

    @property
    def at_floor(self) -> bool:
        return self._epsilon <= self.minimum

    def maybe_random_action(self) -> int | None:
        """Return a random action when exploration triggers, otherwise None."""
        if self._rng.random() >= self._epsilon:
            return None
        self._episode_injections += 1
        self._total_injections += 1
        return self._rng.randrange(self.action_count)

    def episode_completed(self) -> float:
        """Advance the schedule once and return the new epsilon value."""
        self._episodes += 1
        epsilon = max(self.minimum, self._epsilon * self.decay)
        if self.minimum == 0.0 and epsilon < self.cutoff:
            epsilon = 0.0
        self._epsilon = epsilon
        self._episode_injections = 0

        if self.at_floor and not self._floor_logged:
            self.log.info(
                f"Epsilon schedule reached its floor: {self.minimum}"
            )
            self._floor_logged = True
        return self._epsilon

    def reset(self) -> None:
        """Restore the initial schedule and clear all counters."""
        self._epsilon = self.initial
        self._episode_injections = 0
        self._total_injections = 0
        self._episodes = 0
        self._floor_logged = False
