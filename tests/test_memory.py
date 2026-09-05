import unittest

import numpy as np

from snake_lab.memory import ReplayMemory, Transition


class FakeLog:
    def info(self, _message: str) -> None:
        pass


def make_transition(
    value: float, *, done: bool = False, state_size: int = 2
) -> Transition:
    return Transition(
        state=(value,) * state_size,
        action=int(value) % 3,
        reward=value,
        next_state=(value + 0.5,) * state_size,
        done=done,
    )


def make_memory(*, seed: int = 7, max_frames: int = 20) -> ReplayMemory:
    return ReplayMemory(
        state_size=2,
        sequence_length=2,
        batch_size=4,
        max_frames=max_frames,
        seed=seed,
        log=FakeLog(),
    )


class ReplayMemoryTests(unittest.TestCase):
    def test_only_complete_episodes_are_sampled(self) -> None:
        memory = make_memory()
        for value in range(5):
            memory.append(make_transition(float(value)))

        self.assertIsNone(memory.sample())
        self.assertEqual(memory.episode_count, 0)
        self.assertEqual(memory.frame_count, 0)

    def test_sample_is_dense_and_does_not_cross_episode_boundaries(self) -> None:
        memory = make_memory()
        for values in ((0.0, 1.0, 2.0), (10.0, 11.0, 12.0)):
            for index, value in enumerate(values):
                memory.append(
                    make_transition(value, done=index == len(values) - 1)
                )

        batch = memory.sample()

        self.assertIsNotNone(batch)
        self.assertEqual(batch.states.shape, (4, 2, 2))
        self.assertEqual(batch.actions.shape, (4, 2))
        self.assertEqual(batch.rewards.shape, (4, 2))
        self.assertEqual(batch.next_states.shape, (4, 2, 2))
        self.assertEqual(batch.dones.shape, (4, 2))
        self.assertEqual(batch.states.dtype, np.float32)
        self.assertEqual(batch.actions.dtype, np.int64)
        self.assertEqual(batch.dones.dtype, np.bool_)

        sampled_sequences = {
            tuple(sequence[:, 0]) for sequence in batch.states
        }
        self.assertEqual(
            sampled_sequences,
            {(0.0, 1.0), (1.0, 2.0), (10.0, 11.0), (11.0, 12.0)},
        )

    def test_sampling_is_deterministic_for_the_same_seed(self) -> None:
        first = make_memory(seed=19)
        second = make_memory(seed=19)
        for value in range(8):
            transition = make_transition(float(value), done=value == 7)
            first.append(transition)
            second.append(transition)

        np.testing.assert_array_equal(
            first.sample().states,
            second.sample().states,
        )

    def test_oldest_complete_episodes_are_pruned(self) -> None:
        memory = ReplayMemory(
            state_size=2,
            sequence_length=2,
            batch_size=2,
            max_frames=4,
            seed=7,
            log=FakeLog(),
        )
        for values in ((0.0, 1.0, 2.0), (10.0, 11.0, 12.0)):
            for index, value in enumerate(values):
                memory.append(
                    make_transition(value, done=index == len(values) - 1)
                )

        self.assertEqual(memory.episode_count, 1)
        self.assertEqual(memory.frame_count, 3)
        batch = memory.sample()
        self.assertTrue(np.all(batch.states >= 10.0))


if __name__ == "__main__":
    unittest.main()
