"""Logging destinations, thresholds, and application shutdown ownership."""

import asyncio
import io
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from constants.DMyLog import DMyLog
from snake_lab.server import __main__ as entrypoint
from snake_lab.server.SnakeLabServer import SnakeLabServer
from snake_lab.utils.MyLog import MyLog


class MyLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "server.log"
        self.name = f"test.mylog.{uuid4().hex}"
        self.logger = logging.getLogger(self.name)
        self.addCleanup(self.close_handlers)

    def close_handlers(self):
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)

    def test_relative_and_absolute_paths_share_one_destination(self):
        relative = os.path.relpath(self.path)
        first = MyLog(self.name, log_file=relative, to_console=False)
        second = MyLog(self.name, log_file=str(self.path), to_console=False)
        MyLog(self.name, log_file=relative, to_console=False)
        first.info("first message")
        second.info("second message")
        lines = self.path.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn(f"[INFO] [{self.name}] first message", lines[0])
        self.assertIn("second message", lines[1])

    def test_console_reuse_and_no_root_propagation(self):
        output = io.StringIO()
        root_handler = Mock(spec=logging.Handler, level=logging.NOTSET)
        with patch("sys.stderr", output), patch.object(
            logging.getLogger(), "handlers", [root_handler]
        ):
            first = MyLog(self.name)
            second = MyLog(self.name)
            first.info("first")
            second.warning("second")
        self.assertEqual(len(output.getvalue().splitlines()), 2)
        root_handler.handle.assert_not_called()

    def test_level_changes_apply_to_console_and_file(self):
        output = io.StringIO()
        with patch("sys.stderr", output):
            log = MyLog(self.name, log_file=str(self.path), log_level=DMyLog.INFO)
            log.debug("hidden before change")
            log.loglevel(DMyLog.DEBUG)
            log.debug("visible debug")
            log.loglevel(DMyLog.ERROR)
            log.warning("hidden warning")
            log.error("visible error")
        for contents in (output.getvalue(), self.path.read_text()):
            self.assertEqual(len(contents.splitlines()), 2)
            self.assertIn("visible debug", contents)
            self.assertIn("visible error", contents)

    def test_repeated_construction_updates_shared_threshold(self):
        first = MyLog(self.name, log_file=str(self.path), to_console=False,
                      log_level=DMyLog.ERROR)
        second = MyLog(self.name, log_file=str(self.path), to_console=False,
                       log_level=DMyLog.DEBUG)
        first.debug("existing wrapper")
        second.debug("new wrapper")
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    def test_directory_failure_preserves_cause(self):
        parent = Path(self.directory.name) / "file"
        parent.write_text("not a directory")
        with self.assertRaises(RuntimeError) as raised:
            MyLog(self.name, log_file=str(parent / "server.log"), to_console=False)
        self.assertIsInstance(raised.exception.__cause__, OSError)


class LoggingLifecycleTests(unittest.TestCase):
    def test_entrypoint_shuts_down_logging_after_application(self):
        order = []

        async def run():
            order.append("application")

        with patch.object(entrypoint, "amain", run), patch.object(
            entrypoint.logging, "shutdown", side_effect=lambda: order.append("shutdown")
        ):
            entrypoint.main()
        self.assertEqual(order, ["application", "shutdown"])

    def test_entrypoint_shuts_down_logging_on_failure_and_propagates(self):
        failure = RuntimeError("server failed")
        with patch.object(entrypoint, "amain", AsyncMock(side_effect=failure)), patch.object(
            entrypoint.logging, "shutdown"
        ) as shutdown:
            with self.assertRaises(RuntimeError) as raised:
                entrypoint.main()
        self.assertIs(raised.exception, failure)
        shutdown.assert_called_once_with()


class EmbeddedServerLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_cleanup_does_not_close_unrelated_logging(self):
        server = SnakeLabServer.__new__(SnakeLabServer)
        server.endpoint = "unused"
        server._socket = Mock()
        server._context = Mock()
        server._stop_event = asyncio.Event()
        server._stop_event.set()
        server._worker_loop = AsyncMock()
        server._shutdown_worker = AsyncMock()
        server.telemetry = Mock(close=AsyncMock())
        server.events = Mock(close=AsyncMock())
        server.store = Mock()
        server.log = MyLog(f"test.server.{uuid4().hex}", to_console=False)
        with TemporaryDirectory() as directory:
            handler = logging.FileHandler(Path(directory) / "unrelated.log")
            try:
                with patch.object(handler, "close", wraps=handler.close) as close:
                    await server.run()
                    close.assert_not_called()
                self.assertFalse(handler.stream.closed)
            finally:
                handler.close()
                await server._worker_task
        server.store.close.assert_called_once_with()
