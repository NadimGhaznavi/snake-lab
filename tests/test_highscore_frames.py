"""Winning-game capture, persistence atomicity and ZMQ retrieval."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, Mock

import pymysql

from snakelab.client.AsyncLabClient import AsyncLabClient
from snakelab.constants.DGame import Action
from snakelab.database.DbMgr import DatabaseError, DbMgr
from snakelab.database.MemorySimulationStore import MemorySimulationStore
from snakelab.database.SnakeDb import SnakeDb
from snakelab.server.SimulationServer import SimulationServer
from snakelab.zmq.Protocol import METHOD_SIMULATION_HIGHSCORE_FRAMES, PROTOCOL_VERSION
from snakelab.server.Simulator import HighScoreSnapshot
from tests import test_simulator as simulator_tests


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_move_matches_the_game_through_terminal_collision(self):
        simulator = simulator_tests.SimulationLoopTests.capture_simulator()
        simulator.config["game"].update(board_width=8, board_height=8)
        simulator._setup()
        simulator.trainer.train = Mock(return_value=None)
        simulator._select_action = Mock(return_value=int(Action.STRAIGHT))
        result = await simulator._run_episode(1)
        frames = [frame.to_dict() for frame in simulator.state.high_score_frames]
        self.assertGreater(result.steps, 1)
        self.assertEqual([frame["step"] for frame in frames], list(range(result.steps + 1)))
        game = simulator._new_game(1)
        for frame in frames[1:]:
            step = game.step(int(Action.STRAIGHT))
            expected = HighScoreSnapshot(1, step.new_state)
            self.assertEqual(frame, expected.to_dict())
            self.assertEqual(set(frame), {"version", "episode", "step", "board"})
        self.assertTrue(step.done)
        self.assertEqual(frames[-1]["board"]["score"], result.score)

    async def test_capture_without_viewers_latest_tie_and_lower_score(self):
        simulator = simulator_tests.SimulationLoopTests.capture_simulator()
        simulator._setup()
        simulator.trainer.train = Mock(return_value=None)
        for episode, action in ((1, Action.STRAIGHT), (2, Action.STRAIGHT), (3, Action.LEFT)):
            simulator._select_action = Mock(return_value=int(action))
            result = await simulator._run_episode(episode)
            simulator.state.record(result)
        frames = [frame.to_dict() for frame in simulator.state.high_score_frames]
        self.assertEqual([frame["step"] for frame in frames], [0, 1])
        self.assertEqual([frame["episode"] for frame in frames], [2, 2])
        self.assertEqual(set(frames[0]), {"version", "episode", "step", "board"})
        self.assertEqual(frames[0]["version"], 1)
        self.assertEqual(frames[0]["board"]["score"], 0)
        self.assertEqual(frames[1]["board"]["score"], 1)
        self.assertIsNone(frames[1]["board"]["food"])
        self.assertEqual(simulator.state.high_score_snapshot.episode, 2)

    async def test_zero_score_tie_retains_latest_terminal_move(self):
        simulator = simulator_tests.SimulationLoopTests.capture_simulator()
        simulator._setup()
        simulator._select_action = Mock(return_value=int(Action.LEFT))
        for episode in (1, 2):
            result = await simulator._run_episode(episode)
            simulator.state.record(result)
        frames = [frame.to_dict() for frame in simulator.state.high_score_frames]
        self.assertEqual([frame["step"] for frame in frames], [0, 1])
        self.assertEqual(frames[-1]["episode"], 2)
        self.assertEqual(frames[-1]["board"]["score"], 0)
        self.assertEqual(frames[-1]["version"], 1)


class FrameDatabaseTests(unittest.TestCase):
    def test_frames_and_completion_commit_together_or_roll_back(self):
        frames = [{"step": step, "episode": 2} for step in range(3)]
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        store = SnakeDb(DbMgr(connection))
        store.finish_run("run", "completed", 3, 4, high_score_frames=frames)
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 5)
        self.assertIn("DELETE FROM `simulation_high_score_frames`", calls[0].args[0])
        for call, frame in zip(calls[1:4], frames):
            self.assertEqual(call.args[1][:3], ("run", frame["step"], 2))
            self.assertEqual(json.loads(call.args[1][3]), frame)
        self.assertIn("UPDATE `simulation_runs`", calls[-1].args[0])
        connection.commit.assert_called_once()
        connection.reset_mock()
        cursor.execute.side_effect = [None, None, pymysql.IntegrityError(1062, "duplicate")]
        with self.assertRaises(DatabaseError):
            store.finish_run("run", "completed", 3, 4, high_score_frames=frames)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()

    def test_historical_frames_are_decoded_in_move_order(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"run_id": "saved", "status": "completed"}
        cursor.fetchall.return_value = [
            {"step": step, "frame": json.dumps({"step": step})} for step in (2, 0, 1)
        ]
        store = SnakeDb(DbMgr(connection))
        self.assertEqual(store.get_high_score_frames("saved"), {
            "run_id": "saved", "frames": [{"step": step} for step in range(3)],
        })
        connection.commit.assert_called_once()
        cursor.fetchone.return_value = {"run_id": "saved", "status": "running"}
        self.assertIsNone(store.get_high_score_frames("saved")["frames"])
        cursor.fetchone.return_value = None
        self.assertIsNone(store.get_high_score_frames("missing"))


class FrameProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemorySimulationStore()
        self.store.create_run("saved", {}, "test")
        simulator = simulator_tests.SimulationLoopTests.capture_simulator()
        simulator._setup()
        simulator._select_action = Mock(return_value=int(Action.STRAIGHT))
        await simulator._run_episode(1)
        self.frames = [frame.to_dict() for frame in simulator.state.high_score_frames]
        self.store.finish_run("saved", "completed", 1, 1, high_score_frames=self.frames)
        self.server = SimulationServer(store=self.store, log_file=None, port=0)

    async def asyncTearDown(self):
        self.server._socket.close()
        await self.server.telemetry.close()
        await self.server.events.close()
        self.server._context.term()

    def request(self, payload):
        return self.server.handle_request({
            "protocol_version": PROTOCOL_VERSION, "request_id": "capture-request",
            "method": METHOD_SIMULATION_HIGHSCORE_FRAMES, "payload": payload,
        })

    async def test_historical_capture_owns_its_data(self):
        self.assertNotIn("saved", self.server._runs)
        self.frames[0]["board"]["score"] = 99
        response = self.request({"run_id": "saved"})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["payload"]["frames"][0]["board"]["score"], 0)
        response["payload"]["frames"].clear()
        self.assertEqual(len(self.request({"run_id": "saved"})["payload"]["frames"]), 2)

    async def test_unavailable_missing_and_invalid_requests(self):
        self.assertEqual(self.request({"run_id": "unknown"})["error"]["code"], "run_not_found")
        for status in ("queued", "running", "paused", "cancelling", "completed", "failed", "cancelled"):
            self.store.create_run(status, {}, "test")
            self.store.finish_run(status, status, 0, 0)
            self.assertEqual(self.request({"run_id": status})["error"]["code"], "frames_unavailable")
        for payload in ({}, {"run_id": ""}, {"run_id": None}, {"run_id": 3},
                        {"run_id": "saved", "extra": True}):
            self.assertEqual(self.request(payload)["error"]["code"], "invalid_request")

    async def test_frame_round_trip_over_zmq(self):
        port = self.server._socket.bind_to_random_port("tcp://127.0.0.1")
        client = AsyncLabClient(port=port)

        async def serve_once():
            request = await self.server._socket.recv_json()
            await self.server._socket.send_json(self.server.handle_request(request))

        task = asyncio.create_task(serve_once())
        try:
            response = await client.highscore_frames("saved")
            await asyncio.wait_for(task, 3)
            self.assertEqual(response["payload"], {"run_id": "saved", "frames": self.frames})
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            client.close()
