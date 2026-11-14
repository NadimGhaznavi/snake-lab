"""Safe exploration bursts adapted from ai-hydra's EpsilonNice (GPL-3.0).

The original EpsilonNiceAlgo chooses safe alternatives; BehaviourPolicy owns
its probability gate and burst duration. Both behaviors live here so the
policy can use them independently of the neural-network architecture.
"""

import random

from snakelab.constants.DEpsilon import DEpsilon
from snakelab.constants.DGame import Action
from snakelab.constants.DModule import DModule
from snakelab.constants.DMyLog import DMyLogDef
from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.game.GameRules import GameRules
from snakelab.game.GameState import GameState
from snakelab.utils.MyLog import MyLog


class EpsilonNiceAlgo:
    """Occasionally explore safe alternatives after ordinary epsilon expires."""

    def __init__(
        self, *, rng: random.Random, probability: float, steps: int,
        log_file: str | None = DSnakeLab.SERVER_LOG_FILE,
        log: MyLog | None = None,
    ) -> None:
        if not 0 <= probability <= 1:
            raise ValueError("probability must be in the range [0, 1]")
        if type(steps) is not int or steps <= 0:
            raise ValueError("steps must be a positive integer")
        self._rng = rng
        self.probability = probability
        self.steps = steps
        self.log = log or MyLog(
            client_id=DModule.EPSILON_NICE_ALGO,
            log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
            log_file=log_file,
            to_console=False,
        )
        self._calls = 0
        self._triggered = 0
        self._fatal_suggested = 0
        self._overrides = 0
        self._no_safe_alternative = 0
        self.reset_episode()
        self.log.info(
            f"Initialized EpsilonNice: probability={probability}, steps={steps}"
        )

    @property
    def episode_injections(self) -> int:
        return self._episode_injections

    def reset_episode(self) -> None:
        """Discard an unfinished detour when a new game begins."""
        self._steps_remaining = 0
        self._episode_injections = 0

    def select_action(self, suggested_action: int, state: GameState, epsilon: float) -> int:
        if self.probability == 0 or epsilon > DEpsilon.NICE_ACTIVATION_THRESHOLD:
            self._steps_remaining = 0
            return suggested_action

        self._calls += 1
        if self._steps_remaining:
            self._steps_remaining -= 1
            return self.override_action(suggested_action, state)

        # Match Hydra: a successful gate starts the detour on the next move.
        if self._rng.random() < self.probability:
            self._steps_remaining = self.steps
        return suggested_action

    def override_action(self, suggested_action: int, state: GameState) -> int:
        """Choose a safe different move; retain the suggestion if none exists."""
        self._triggered += 1
        alternatives = [
            action for action in Action
            if action != suggested_action and not GameRules.would_collide(state, action)
        ]
        if not alternatives:
            self._no_safe_alternative += 1
            return suggested_action
        if GameRules.would_collide(state, suggested_action):
            self._fatal_suggested += 1
        self._overrides += 1
        self._episode_injections += 1
        return int(self._rng.choice(alternatives))

    def get_stats(self) -> dict[str, int | float]:
        """Return cumulative statistics; episode counts travel with results."""
        return {
            "calls": self._calls,
            "triggered": self._triggered,
            "fatal_suggested": self._fatal_suggested,
            "overrides": self._overrides,
            "no_safe_alternative": self._no_safe_alternative,
            "trigger_rate": self._triggered / self._calls if self._calls else 0.0,
            "override_rate": self._overrides / self._calls if self._calls else 0.0,
        }
