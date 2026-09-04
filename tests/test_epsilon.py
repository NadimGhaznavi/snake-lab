import random
import unittest

from snake_lab.epsilon import EpsilonAlgo


class FakeLog:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class EpsilonAlgoTests(unittest.TestCase):
    def test_zero_epsilon_never_injects_an_action(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=0,
            minimum=0,
            decay=1,
            log=FakeLog(),
        )

        self.assertTrue(
            all(epsilon.maybe_random_action() is None for _ in range(100))
        )
        self.assertEqual(epsilon.episode_injections, 0)

    def test_full_epsilon_always_returns_a_valid_action(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=1,
            minimum=0,
            decay=1,
            log=FakeLog(),
        )

        actions = [epsilon.maybe_random_action() for _ in range(100)]

        self.assertTrue(all(action in (0, 1, 2) for action in actions))
        self.assertEqual(epsilon.episode_injections, 100)
        self.assertEqual(epsilon.total_injections, 100)

    def test_same_rng_seed_produces_the_same_decisions(self) -> None:
        first = EpsilonAlgo(
            rng=random.Random(19),
            initial=0.5,
            minimum=0,
            decay=0.97,
            log=FakeLog(),
        )
        second = EpsilonAlgo(
            rng=random.Random(19),
            initial=0.5,
            minimum=0,
            decay=0.97,
            log=FakeLog(),
        )

        self.assertEqual(
            [first.maybe_random_action() for _ in range(100)],
            [second.maybe_random_action() for _ in range(100)],
        )

    def test_episode_completion_decays_to_configured_minimum(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=0.8,
            minimum=0.2,
            decay=0.5,
            log=FakeLog(),
        )

        self.assertEqual(epsilon.episode_completed(), 0.4)
        self.assertEqual(epsilon.episode_completed(), 0.2)
        self.assertEqual(epsilon.episode_completed(), 0.2)
        self.assertTrue(epsilon.at_floor)
        self.assertEqual(epsilon.episodes, 3)

    def test_zero_minimum_uses_explicit_cutoff(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=0.0015,
            minimum=0,
            decay=0.5,
            cutoff=0.001,
            log=FakeLog(),
        )

        self.assertEqual(epsilon.episode_completed(), 0.0)
        self.assertTrue(epsilon.at_floor)

    def test_episode_completion_resets_only_episode_counter(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=1,
            minimum=0,
            decay=1,
            log=FakeLog(),
        )
        epsilon.maybe_random_action()

        epsilon.episode_completed()

        self.assertEqual(epsilon.episode_injections, 0)
        self.assertEqual(epsilon.total_injections, 1)

    def test_reset_restores_schedule_and_counters(self) -> None:
        epsilon = EpsilonAlgo(
            rng=random.Random(7),
            initial=1,
            minimum=0,
            decay=0.5,
            log=FakeLog(),
        )
        epsilon.maybe_random_action()
        epsilon.episode_completed()

        epsilon.reset()

        self.assertEqual(epsilon.current, 1.0)
        self.assertEqual(epsilon.episodes, 0)
        self.assertEqual(epsilon.episode_injections, 0)
        self.assertEqual(epsilon.total_injections, 0)

    def test_invalid_schedule_is_rejected(self) -> None:
        cases = (
            {"initial": 1.1},
            {"minimum": -0.1},
            {"decay": 0},
            {"initial": 0.2, "minimum": 0.3},
        )
        for values in cases:
            with self.subTest(values=values):
                schedule = {
                    "initial": 0.96,
                    "minimum": 0.0,
                    "decay": 0.97,
                }
                schedule.update(values)
                with self.assertRaises((TypeError, ValueError)):
                    EpsilonAlgo(
                        rng=random.Random(7),
                        log=FakeLog(),
                        **schedule,
                    )


if __name__ == "__main__":
    unittest.main()
