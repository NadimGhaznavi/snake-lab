import unittest

import numpy as np

from snake_lab.memory import ReplayMemory, Transition


class FakeLog:
    def info(self, _message: str) -> None:
        pass


def make_transition(value: float, *, done: bool = False) -> Transition:
    return Transition(
        state=(value, value), action=int(value) % 3, reward=value,
        next_state=(value + 0.5, value + 0.5), done=done,
    )


def make_memory(**overrides) -> ReplayMemory:
    return ReplayMemory(**{
        "state_size": 2, "sequence_length": 2, "batch_size": 1,
        "max_frames": 100, "min_episodes": 1, "seed": 7,
        "log": FakeLog(), **overrides,
    })


def append_episode(memory, values):
    for index, value in enumerate(values):
        memory.append(make_transition(float(value), done=index == len(values) - 1))


class ReplayMemoryTests(unittest.TestCase):
    def test_only_complete_episodes_count_toward_warmup(self):
        memory = make_memory(min_episodes=3)
        append_episode(memory, [0, 1, 2])
        append_episode(memory, [10, 11])
        self.assertIsNone(memory.sample())
        memory.append(make_transition(20))
        self.assertIsNone(memory.sample())
        memory.append(make_transition(21, done=True))
        self.assertEqual(memory.episode_count, 3)
        self.assertIsNotNone(memory.sample())

    def test_chunks_are_aligned_to_terminal_move(self):
        memory = make_memory(sequence_length=4)
        append_episode(memory, list(range(10)))
        batch = memory.sample()
        self.assertEqual(batch.states.shape, (2, 4, 2))
        np.testing.assert_array_equal(batch.states[:, :, 0], [[2, 3, 4, 5], [6, 7, 8, 9]])
        np.testing.assert_array_equal(batch.next_states[:, :, 0], [[2.5, 3.5, 4.5, 5.5], [6.5, 7.5, 8.5, 9.5]])
        np.testing.assert_array_equal(batch.rewards, [[2, 3, 4, 5], [6, 7, 8, 9]])
        self.assertTrue(batch.dones[-1, -1])
        self.assertEqual(batch.dones.sum(), 1)
        self.assertEqual(memory.frame_count, 8)
        self.assertEqual(batch.states.dtype, np.float32)
        self.assertEqual(batch.actions.dtype, np.int64)
        self.assertEqual(batch.dones.dtype, np.bool_)

    def test_multiple_games_have_independent_chunks(self):
        memory = make_memory(batch_size=2)
        append_episode(memory, [0, 1, 2])
        self.assertIsNone(memory.sample())
        append_episode(memory, [10, 11, 12, 13])
        batch = memory.sample()
        self.assertEqual(batch.states.shape, (3, 2, 2))
        self.assertEqual({tuple(row) for row in batch.states[:, :, 0]}, {(1, 2), (10, 11), (12, 13)})
        self.assertEqual(batch.dones.sum(), 2)

    def test_single_game_batch_selects_all_retained_chunks(self):
        memory = make_memory()
        append_episode(memory, [0, 1])
        append_episode(memory, [10, 11, 12, 13])
        seen = set()
        for _ in range(30):
            rewards = tuple(memory.sample().rewards.flatten())
            self.assertIn(rewards, {(0, 1), (10, 11, 12, 13)})
            seen.add(rewards)
        self.assertEqual(len(seen), 2)

    def test_append_stores_chunks_and_single_game_sampling_reuses_them(self):
        memory = make_memory(sequence_length=4)
        append_episode(memory, list(range(10)))
        stored = memory._episodes[0]
        self.assertEqual(stored.states.shape, (2, 4, 2))
        self.assertEqual(stored.actions.shape, (2, 4))
        self.assertEqual(stored.size, 8)
        batch = memory.sample()
        for field in ("states", "actions", "rewards", "next_states", "dones"):
            self.assertIs(getattr(batch, field), getattr(stored, field))

    def test_short_games_are_discarded_and_do_not_count(self):
        memory = make_memory(sequence_length=4)
        for size in (1, 2, 3):
            append_episode(memory, list(range(size)))
        self.assertEqual(memory.episode_count, 0)
        self.assertEqual(memory.frame_count, 0)
        self.assertIsNone(memory.sample())
        append_episode(memory, [10, 11, 12, 13])
        self.assertEqual(memory.episode_count, 1)
        np.testing.assert_array_equal(memory.sample().rewards, [[10, 11, 12, 13]])

    def test_sampling_is_deterministic_for_the_same_seed(self):
        first, second = make_memory(), make_memory()
        for memory in (first, second):
            append_episode(memory, [0, 1, 2])
            append_episode(memory, [10, 11])
        for _ in range(5):
            np.testing.assert_array_equal(first.sample().states, second.sample().states)

    def test_eviction_reapplies_stored_episode_threshold(self):
        memory = make_memory(max_frames=6, min_episodes=2)
        append_episode(memory, [0, 1])
        append_episode(memory, [10, 11])
        self.assertIsNotNone(memory.sample())
        append_episode(memory, [20, 21, 22, 23, 24, 25])
        self.assertEqual(memory.episode_count, 1)
        self.assertEqual(memory.frame_count, 6)
        self.assertIsNone(memory.sample())

    def test_one_move_game_and_sequence_length_one(self):
        memory = make_memory(sequence_length=1)
        append_episode(memory, [5])
        batch = memory.sample()
        self.assertEqual(batch.states.shape, (1, 1, 2))
        np.testing.assert_array_equal(batch.next_states, [[[5.5, 5.5]]])

    def test_invalid_minimum_is_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_memory(min_episodes=value)
        with self.assertRaises(ValueError):
            make_memory(max_frames=2, min_episodes=3)
