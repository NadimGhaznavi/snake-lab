import unittest
from collections import deque
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from snake_lab.zmq.FrameTelemetry import FrameTelemetry

import torch

from constants.DGame import DGameDef
from constants.DSnakeLab import DSnakeLab
from snake_lab.server.Configuration import simulation_config_template
from snake_lab.server.Simulator import Simulator
from snake_lab.nn.ReplayMemory import ReplayMemory
from constants.DGame import Action
from constants.DGame import Outcome


class FakeDevice:
    def __init__(self, device_type: str) -> None:
        self.type = device_type


class FakeTensor:
    def __add__(self, _value: int) -> "FakeTensor":
        return self

    def sum(self) -> "FakeTensor":
        return self

    def item(self) -> float:
        return 2.0


class FakeCuda:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.synchronized = False

    def is_available(self) -> bool:
        return self.available

    def get_device_name(self, _device: FakeDevice) -> str:
        return "Test GPU"

    def synchronize(self, _device: FakeDevice) -> None:
        self.synchronized = True


class FakeTorch:
    def __init__(self, cuda_available: bool) -> None:
        self.cuda = FakeCuda(cuda_available)
        self.tensor_device: FakeDevice | None = None

    def set_num_threads(self, count: int) -> None:
        self.num_threads = count

    def get_num_threads(self) -> int:
        return self.num_threads

    def get_num_interop_threads(self) -> int:
        return 8

    @staticmethod
    def device(device_type: str) -> FakeDevice:
        return FakeDevice(device_type)

    def ones(self, _size: int, device: FakeDevice) -> FakeTensor:
        self.tensor_device = device
        return FakeTensor()


class FakeLog:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def debug(self, _message: str) -> None:
        pass


class GreedyEpsilon:
    @staticmethod
    def maybe_random_action() -> None:
        return None


class CapturingModel:
    def __init__(self) -> None:
        self.input_shape = None

    def eval(self) -> None:
        pass

    def __call__(self, states):
        self.input_shape = states.shape
        return torch.tensor([[0.0, 2.0, 1.0]])


class SimulatorTests(unittest.TestCase):
    def test_cpu_runtime(self) -> None:
        torch_module = FakeTorch(cuda_available=False)
        log = FakeLog()

        simulator = Simulator(
            simulation_config_template().resolve({"epochs": 1500}),
            torch_module=torch_module, log=log
        )
        simulator.probe_runtime()

        self.assertEqual(
            simulator.runtime_description,
            f"Simulation running on CPU: torch_threads={DSnakeLab.PYTORCH_NUM_THREADS}, torch_interop_threads=8",
        )
        self.assertEqual(log.messages, [simulator.runtime_description])
        self.assertEqual(torch_module.tensor_device.type, "cpu")
        self.assertFalse(torch_module.cuda.synchronized)

    def test_cpu_runtime_even_when_cuda_is_available(self) -> None:
        torch_module = FakeTorch(cuda_available=True)
        log = FakeLog()

        simulator = Simulator(
            simulation_config_template().resolve({"epochs": 1500}),
            torch_module=torch_module, log=log
        )
        simulator.probe_runtime()

        self.assertEqual(
            simulator.runtime_description,
            f"Simulation running on CPU: torch_threads={DSnakeLab.PYTORCH_NUM_THREADS}, torch_interop_threads=8",
        )
        self.assertEqual(
            log.messages, [simulator.runtime_description]
        )
        self.assertEqual(torch_module.tensor_device.type, "cpu")
        self.assertFalse(torch_module.cuda.synchronized)

    def test_model_and_trainer_stay_on_cpu_when_cuda_is_available(self) -> None:
        with patch("torch.cuda.is_available", return_value=True):
            simulator = Simulator(
                SimulationLoopTests.small_config(), log=FakeLog(),
            )
            simulator._setup()
        self.assertEqual(simulator.device.type, "cpu")
        self.assertEqual(simulator.trainer.device.type, "cpu")
        for model in (simulator.model, simulator.trainer.target_model):
            self.assertTrue(all(p.device.type == "cpu" for p in model.parameters()))

    def test_episode_seeds_are_independent_and_reproducible(self) -> None:
        config = simulation_config_template().resolve({"epochs": 100})
        first = Simulator(config, log=FakeLog())
        second = Simulator(config, log=FakeLog())

        first_seeds = [first._new_game(index).seed for index in (1, 2)]
        second_seeds = [second._new_game(index).seed for index in (1, 2)]

        self.assertEqual(first_seeds, second_seeds)
        self.assertNotEqual(first_seeds[0], first_seeds[1])

    def test_policy_receives_the_complete_rolling_window(self) -> None:
        simulator = Simulator(
            simulation_config_template().resolve({"epochs": 100}), log=FakeLog()
        )
        model = CapturingModel()
        simulator.model = model
        simulator.epsilon = GreedyEpsilon()
        history = deque(
            [
                tuple([float(index)] * DGameDef.OBSERVATION_SIZE)
                for index in range(4)
            ],
            maxlen=4,
        )

        action = simulator._select_action(history)

        self.assertEqual(action, 1)
        self.assertEqual(
            model.input_shape,
            torch.Size([4, DGameDef.OBSERVATION_SIZE]),
        )


class SimulationLoopTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def capture_simulator():
        simulator = Simulator(simulation_config_template().resolve({}), log=FakeLog())
        # Exercise tiny game mechanics without relaxing the public config schema.
        simulator.config["game"].update(
            board_width=4, board_height=1, initial_snake_length=3,
            max_moves_multiplier=1,
        )
        return simulator

    async def test_capture_keeps_first_peak_of_best_completed_episode(self) -> None:
        simulator = self.capture_simulator()
        simulator._setup()
        simulator.trainer.train = Mock(return_value=None)
        simulator._select_action = Mock(return_value=0)
        initial_game = simulator._new_game(1)
        initial = initial_game.state
        observation = initial_game.observe()

        async def episode(number, score):
            peak = replace(initial, score=score, move_count=1)
            terminal = replace(peak, move_count=4)
            game = Mock(state=initial, seed=initial.seed)
            game.observe.return_value = observation
            states = iter((peak, terminal))

            def step(_action):
                game.state = next(states)
                return SimpleNamespace(
                    new_state=game.state, observation=observation, reward=0.0,
                    done=game.state is terminal, outcome=Outcome.WALL,
                )

            game.step.side_effect = step
            with patch.object(simulator, "_new_game", return_value=game):
                result = await simulator._run_episode(number)
            simulator.state.record(result)
            return peak

        first = await episode(1, 1)
        self.assertIs(simulator.state.high_score_snapshot.board, first)
        await episode(2, 1)
        self.assertIs(simulator.state.high_score_snapshot.board, first)
        best = await episode(3, 2)
        snapshot = simulator.state.high_score_snapshot
        self.assertIs(snapshot.board, best)
        self.assertEqual(snapshot.episode, 3)
        self.assertEqual(snapshot.to_dict()["step"], 1)
        self.assertEqual(snapshot.to_dict()["board"]["score"], 2)
        simulator.trainer.train.side_effect = RuntimeError("training failed")
        with self.assertRaisesRegex(RuntimeError, "training failed"):
            await episode(4, 3)
        self.assertIs(simulator.state.high_score_snapshot, snapshot)

    async def test_zero_score_and_board_filling_capture_without_telemetry(self) -> None:
        for action, expected_score in ((Action.LEFT, 0), (Action.STRAIGHT, 1)):
            with self.subTest(action=action):
                simulator = self.capture_simulator()
                simulator._setup()
                simulator._select_action = Mock(return_value=int(action))
                initial = simulator._new_game(1).state
                result = await simulator._run_episode(1)
                snapshot = simulator.state.high_score_snapshot
                self.assertEqual(result.score, expected_score)
                self.assertEqual(snapshot.board.score, expected_score)
                self.assertEqual(snapshot.board.move_count, expected_score)
                if expected_score == 0:
                    self.assertEqual(snapshot.board, initial)
                else:
                    self.assertIsNone(snapshot.to_dict()["board"]["food"])

    @staticmethod
    def small_config():
        return simulation_config_template().resolve(
            {
                "epochs": 100,
                "seed": 7,
                "model": {"hidden_size": 64},
                "training": {"sequence_length": 4, "batch_size": 8},
            }
        )

    async def test_run_executes_complete_episodes_and_training(self) -> None:
        config = self.small_config()
        completed = []
        frames = []
        simulator = Simulator(
            config,
            log=FakeLog(),
            on_episode=lambda result, _state: completed.append(result),
            on_frame=frames.append,
        )

        with patch.object(
            ReplayMemory, "append", autospec=True, side_effect=ReplayMemory.append
        ) as append:
            state = await simulator.run()

        transitions = [call.args[1] for call in append.call_args_list]
        self.assertEqual(len(transitions), state.total_steps)
        self.assertEqual(sum(item.done for item in transitions), 100)
        for previous, current in zip(transitions, transitions[1:]):
            if not previous.done:
                self.assertEqual(previous.next_state, current.state)

        self.assertEqual(state.completed_epochs, 100)
        self.assertEqual(
            state.total_steps, sum(result.steps for result in state.episodes)
        )
        self.assertEqual(len(state.episodes), 100)
        self.assertEqual(len(completed), 100)
        self.assertEqual(len(frames), state.total_steps)
        self.assertTrue(frames[-1].done)
        self.assertEqual(sum(frame.done for frame in frames), 100)
        self.assertEqual(
            simulator.replay.episode_count,
            sum(result.steps >= 4 for result in state.episodes),
        )
        self.assertIsNotNone(state.last_loss)

    async def test_frame_construction_tracks_demand_during_run(self) -> None:
        frames = []
        demand = False

        def completed(result, _state):
            nonlocal demand
            # Join after episode 20 and leave after episode 40.
            demand = 20 <= result.episode < 40

        simulator = Simulator(
            self.small_config(), log=FakeLog(), on_episode=completed,
            on_frame=frames.append, frame_enabled=lambda: demand,
        )
        with patch.object(
            FrameTelemetry, "from_step", wraps=FrameTelemetry.from_step
        ) as construct:
            state = await simulator.run()
        self.assertEqual(state.completed_epochs, 100)
        self.assertEqual(
            state.total_steps, sum(result.steps for result in state.episodes)
        )
        expected_episodes = [
            result.episode
            for result in state.episodes[20:40]
            for _ in range(result.steps)
        ]
        self.assertEqual(construct.call_count, len(expected_episodes))
        self.assertEqual([item.episode for item in frames], expected_episodes)
        self.assertEqual(
            simulator.replay.episode_count,
            sum(result.steps >= 4 for result in state.episodes),
        )
        self.assertIsNotNone(state.last_loss)

    async def test_no_viewer_constructs_no_frames(self) -> None:
        simulator = Simulator(
            self.small_config(), log=FakeLog(), on_frame=lambda frame: None,
            frame_enabled=lambda: False,
        )
        with patch.object(FrameTelemetry, "from_step") as construct:
            state = await simulator.run()
        construct.assert_not_called()
        self.assertEqual(state.completed_epochs, 100)
        self.assertEqual(
            simulator.replay.episode_count,
            sum(result.steps >= 4 for result in state.episodes),
        )


if __name__ == "__main__":
    unittest.main()
