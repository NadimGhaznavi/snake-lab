"""Verify listener configuration at its file and consumer boundaries."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from snakelab.constants.DSnakeLab import DSnakeLab
from snakelab.Network import Network
from snakelab.NetworkConfiguration import NetworkConfiguration


class NetworkConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "snakelab.json"
        Network.configuration.cache_clear()
        self.addCleanup(Network.configuration.cache_clear)
        config_path = patch.object(DSnakeLab, "NETWORK_CONFIG_FILE", str(self.path))
        config_path.start()
        self.addCleanup(config_path.stop)

    def write(self, data):
        self.path.write_text(json.dumps(data))

    def test_missing_file_and_partial_overrides(self):
        config = NetworkConfiguration(self.path)
        for use, interface, port in DSnakeLab.CMDB_NETWORK:
            self.assertEqual(config.binding(use), (interface, port))
        self.write({"network": {"control": {"port": 42970},
                                "telemetry": {"interface": "192.0.2.15"}}})
        config = NetworkConfiguration(self.path)
        self.assertEqual(config.binding("control"), ("0.0.0.0", 42970))
        self.assertEqual(config.destination("control"), ("127.0.0.1", 42970))
        self.assertEqual(config.destination("telemetry")[0], "192.0.2.15")
        self.assertEqual(config.binding("events"), Network.binding("events"))

    def test_invalid_files_fail_with_path_and_setting(self):
        invalid = [([], "object"), ({"other": {}}, "network"),
                   ({"network": []}, "network"),
                   ({"network": {"unknown": {}}}, "unknown"),
                   ({"network": {"control": {"host": "127.0.0.1"}}}, "control"),
                   ({"network": {"control": []}}, "control")]
        for value in [True, "41970", 0, 65536, None, 1.5]:
            invalid.append(({"network": {"control": {"port": value}}}, "port"))
        for value in ["*", "localhost", "::1", "999.0.0.1", 123, None]:
            invalid.append(({"network": {"control": {"interface": value}}}, "interface"))
        for data, setting in invalid:
            with self.subTest(data=data):
                self.write(data)
                with self.assertRaisesRegex(ValueError, setting) as caught:
                    NetworkConfiguration(self.path)
                self.assertIn(str(self.path), str(caught.exception))
        self.path.write_text("{")
        with self.assertRaisesRegex(ValueError, str(self.path)):
            NetworkConfiguration(self.path)

    def test_create_uses_declaration_and_preserves_existing_file(self):
        NetworkConfiguration.create(self.path)
        self.assertEqual(json.loads(self.path.read_text()), {"network": {
            use: {"interface": interface, "port": port}
            for use, interface, port in DSnakeLab.CMDB_NETWORK
        }})
        self.write({"network": {"events": {"port": 42972}}})
        before = self.path.read_bytes()
        NetworkConfiguration.create(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_configuration_is_a_process_snapshot(self):
        self.assertEqual(Network.binding("control")[1], 41970)
        self.write({"network": {"control": {"port": 42970}}})
        self.assertEqual(Network.binding("control")[1], 41970)
        Network.configuration.cache_clear()  # A new process reloads its settings.
        self.assertEqual(Network.binding("control")[1], 42970)

    def test_consumers_follow_changed_declaration_and_explicit_overrides(self):
        from snakelab.client import SnakeLabClient
        from snakelab.client.AsyncLabClient import AsyncLabClient
        from snakelab.server.SimulationServer import SimulationServer

        with patch.object(DSnakeLab, "CMDB_NETWORK", (
            ("events", "192.0.2.3", 42972),
            ("control", "0.0.0.0", 42970),
            ("telemetry", "192.0.2.2", 42971),
        )):
            server = SimulationServer(log_file=None)
            self.addCleanup(server._context.term)
            self.addCleanup(server._socket.close)
            self.addCleanup(server.telemetry._socket.close)
            self.addCleanup(server.events._socket.close)
            self.assertEqual(server.endpoint, "tcp://0.0.0.0:42970")
            self.assertEqual(server.telemetry.endpoint, "tcp://192.0.2.2:42971")
            self.assertEqual(server.events.endpoint, "tcp://192.0.2.3:42972")
            client = AsyncLabClient()
            self.addCleanup(client.close)
            self.assertEqual(client.endpoint, "tcp://127.0.0.1:42970")
            tui = SnakeLabClient()
            self.assertEqual((tui._host, tui._control_port), ("127.0.0.1", 42970))
            self.assertEqual((tui._telemetry_host, tui._telemetry_port), ("192.0.2.2", 42971))
            explicit = AsyncLabClient(host="example.org", port=43970)
            self.addCleanup(explicit.close)
            self.assertEqual(explicit.endpoint, "tcp://example.org:43970")
            server_override = SimulationServer(address="127.0.0.2", port=43970,
                                               telemetry_port=43971, events_port=43972,
                                               log_file=None)
            self.addCleanup(server_override._context.term)
            self.addCleanup(server_override._socket.close)
            self.addCleanup(server_override.telemetry._socket.close)
            self.addCleanup(server_override.events._socket.close)
            self.assertEqual(server_override.endpoint, "tcp://127.0.0.2:43970")
            self.assertEqual(server_override.telemetry.endpoint, "tcp://127.0.0.2:43971")
            self.assertEqual(server_override.events.endpoint, "tcp://127.0.0.2:43972")
