import asyncio
import json
import unittest
from unittest.mock import MagicMock

from snake_lab.control_client import AsyncLabClient
from snake_lab.database import MariaDBSimulationStore, MemorySimulationStore
from snake_lab.protocol import METHOD_SIMULATION_HIGHSCORE_SNAPSHOT, PROTOCOL_VERSION
from snake_lab.server import SnakeLabServer
from snake_lab.telemetry import BoardSnapshot


SNAPSHOT = {
    "version": 1, "episode": 3, "step": 7,
    "board": {
        "grid_size": [4, 1], "snake_head": [3, 0],
        "snake_body": [[2, 0], [1, 0], [0, 0]],
        "food": None, "direction": [1, 0], "score": 1,
    },
}


class SnapshotLookupTests(unittest.TestCase):
    def test_database_decodes_snapshot_and_ends_read_transaction(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        store = MariaDBSimulationStore(connection)
        for value in (json.dumps(SNAPSHOT), None):
            cursor.fetchone.return_value = {"run_id": "saved", "high_score_snapshot": value}
            row = store.get_high_score_snapshot("saved")
            self.assertEqual(row["high_score_snapshot"], SNAPSHOT if value else None)
            self.assertEqual(cursor.execute.call_args.args[1], ("saved",))
        cursor.fetchone.return_value = None
        self.assertIsNone(store.get_high_score_snapshot("missing"))
        self.assertEqual(connection.commit.call_count, 3)
        cursor.execute.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            store.get_high_score_snapshot("saved")
        connection.rollback.assert_called_once()


class SnapshotProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemorySimulationStore()
        self.store.create_run("saved", {}, "test")
        self.store.finish_run("saved", "completed", 3, 1, high_score_snapshot=SNAPSHOT)
        self.server = SnakeLabServer(store=self.store, log_file=None, port=0)

    async def asyncTearDown(self):
        self.server._socket.close()
        await self.server.telemetry.close()
        await self.server.events.close()
        self.server._context.term()

    def request(self, payload):
        return self.server.handle_request({
            "protocol_version": PROTOCOL_VERSION, "request_id": "snapshot-request",
            "method": METHOD_SIMULATION_HIGHSCORE_SNAPSHOT, "payload": payload,
        })

    async def test_historical_run_does_not_require_in_memory_run(self):
        self.assertNotIn("saved", self.server._runs)
        response = self.request({"run_id": "saved"})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["request_id"], "snapshot-request")
        self.assertEqual(response["payload"], {"run_id": "saved", "snapshot": SNAPSHOT})
        BoardSnapshot.from_dict(response["payload"]["snapshot"]["board"])
        response["payload"]["snapshot"]["board"]["score"] = 99
        self.assertEqual(self.request({"run_id": "saved"})["payload"]["snapshot"], SNAPSHOT)

    async def test_missing_and_unavailable_snapshots(self):
        self.assertEqual(self.request({"run_id": "unknown"})["error"]["code"], "run_not_found")
        for status in ("queued", "running", "completed", "cancelled", "failed"):
            self.store.create_run(status, {}, "test")
            self.store.set_status(status, status)
            self.assertEqual(
                self.request({"run_id": status})["error"]["code"], "snapshot_unavailable"
            )

    async def test_invalid_payloads(self):
        for payload in ({}, {"run_id": ""}, {"run_id": None}, {"run_id": 3},
                        {"run_id": "saved", "extra": True}):
            with self.subTest(payload=payload):
                self.assertEqual(self.request(payload)["error"]["code"], "invalid_request")

    async def test_raw_snapshot_round_trip_over_zmq(self):
        port = self.server._socket.bind_to_random_port("tcp://127.0.0.1")
        client = AsyncLabClient(port=port)

        async def serve_once():
            request = await self.server._socket.recv_json()
            await self.server._socket.send_json(self.server.handle_request(request))

        task = asyncio.create_task(serve_once())
        try:
            response = await client.highscore_snapshot("saved")
            await asyncio.wait_for(task, 3)
            self.assertEqual(response["payload"], {"run_id": "saved", "snapshot": SNAPSHOT})
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            client.close()
