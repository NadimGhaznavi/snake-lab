import unittest
from random import Random

import numpy as np

from snake_lab.nn.ReplayMemory import ReplayMemory, Transition


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
        next_state=(value + 1.0,) * state_size,
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
        self.assertEqual(batch.actions.shape, (4,))
        self.assertEqual(batch.rewards.shape, (4,))
        self.assertEqual(batch.next_states.shape, (4, 2, 2))
        self.assertEqual(batch.dones.shape, (4,))
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
        np.testing.assert_array_equal(batch.next_states, batch.states + 1)

    def test_compact_storage_preserves_terminal_observation_and_transition_fields(self) -> None:
        memory = make_memory()
        transitions = [make_transition(float(value)) for value in range(4)]
        transitions.append(Transition((4.0, 4.0), 2, -7.0, (99.0, 98.0), True))
        for transition in transitions:
            memory.append(transition)

        episode = memory._episodes[0]
        self.assertEqual(episode.states.shape, (6, 2))
        self.assertEqual(episode.size, 5)
        self.assertTrue(episode.states.flags.c_contiguous)
        self.assertEqual(episode.states.nbytes, 6 * 2 * 4)
        self.assertFalse(hasattr(episode, "next_states"))
        self.assertTrue(np.shares_memory(episode.states[:-1], episode.states[1:]))

        batch = memory.sample()
        for index, states in enumerate(batch.states):
            start = int(states[0, 0])
            window = transitions[start:start + 2]
            for field in ("state", "next_state"):
                np.testing.assert_array_equal(
                    getattr(batch, field + "s")[index],
                    [getattr(transition, field) for transition in window],
                )
            for field in ("action", "reward", "done"):
                self.assertEqual(
                    getattr(batch, field + "s")[index],
                    getattr(window[-1], field),
                )

    def test_single_transition_episode_keeps_both_observations(self) -> None:
        memory = ReplayMemory(
            state_size=2, sequence_length=1, batch_size=1,
            max_frames=1, seed=7, log=FakeLog(),
        )
        memory.append(Transition((1.0, 2.0), 0, 3.0, (8.0, 9.0), True))
        batch = memory.sample()
        np.testing.assert_array_equal(batch.states, [[[1.0, 2.0]]])
        np.testing.assert_array_equal(batch.next_states, [[[8.0, 9.0]]])
        np.testing.assert_array_equal(batch.dones, [True])

    def test_sampling_reuses_and_fully_overwrites_all_five_buffers(self) -> None:
        memory = make_memory(max_frames=8)
        for value in range(5):
            memory.append(make_transition(float(value), done=value == 4))
        first = memory.sample()
        saved_states = first.states.copy()
        for value in range(10, 15):
            memory.append(make_transition(float(value), done=value == 14))
        second = memory.sample()
        for field in ("states", "next_states", "actions", "rewards", "dones"):
            self.assertIs(getattr(first, field), getattr(second, field))
        self.assertTrue(np.all(saved_states < 10))
        self.assertTrue(np.all(second.states >= 10))
        np.testing.assert_array_equal(second.next_states, second.states + 1)
        final_values = second.states[:, -1, 0]
        np.testing.assert_array_equal(second.actions, final_values % 3)
        np.testing.assert_array_equal(second.rewards, final_values)
        np.testing.assert_array_equal(second.dones, final_values == 14)

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

    def test_cached_windows_preserve_seeded_sampling_during_open_episode(self) -> None:
        memory = make_memory(seed=19)
        for values in ((0.0,), (10.0, 11.0, 12.0), (20.0, 21.0, 22.0, 23.0)):
            for index, value in enumerate(values):
                memory.append(make_transition(value, done=index == len(values) - 1))

        windows = np.asarray(
            ((10, 11), (11, 12), (20, 21), (21, 22), (22, 23)),
            dtype=np.float32,
        )
        rng = Random(19)
        for value in range(5):
            memory.append(make_transition(float(100 + value)))
            batch = memory.sample()
            np.testing.assert_array_equal(
                batch.states[:, :, 0], windows[rng.sample(range(5), 4)]
            )

    def test_short_episode_eviction_updates_available_windows(self) -> None:
        memory = make_memory(max_frames=8)
        for value in range(5):
            memory.append(make_transition(float(value), done=value == 4))
        self.assertIsNotNone(memory.sample())

        for value in range(4):
            memory.append(make_transition(float(100 + value), done=True))

        self.assertEqual(memory.frame_count, 4)
        self.assertEqual(memory.episode_count, 4)
        self.assertIsNone(memory.sample())

    def test_oversized_episode_clears_windows_and_next_episode_repopulates(self) -> None:
        memory = make_memory(max_frames=8)
        for length in (5, 9):
            for value in range(length):
                memory.append(make_transition(float(value), done=value == length - 1))
        self.assertEqual(memory.episode_count, 0)
        self.assertEqual(memory.frame_count, 0)
        self.assertIsNone(memory.sample())

        for value in range(5):
            memory.append(make_transition(float(100 + value), done=value == 4))
        batch = memory.sample()
        self.assertEqual(
            {tuple(sequence[:, 0]) for sequence in batch.states},
            {(100, 101), (101, 102), (102, 103), (103, 104)},
        )


if __name__ == "__main__":
    unittest.main()
