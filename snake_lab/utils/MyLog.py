"""Consistent console and file logging for SnakeLab components."""

import logging
from pathlib import Path
from typing import Any

from constants.DMyLog import LOG_LEVELS, DMyLog, DMyLogDef


class MyLog:
    """Wrap a named logger, sharing its handlers across component instances.

    Destinations are added once per logger. The latest configured log level
    applies to all instances using that name. Process shutdown belongs to the
    application entry point.
    """

    def __init__(
        self,
        client_id: str,
        log_file: str | None = None,
        to_console: bool = True,
        log_level: DMyLog = DMyLogDef.DEFAULT_LOG_LEVEL,
    ) -> None:
        self._logger = logging.getLogger(client_id)
        self._logger.setLevel(LOG_LEVELS[log_level])
        self._logger.propagate = False

        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if to_console:
            has_console = any(
                isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
                for h in self._logger.handlers
            )
            if not has_console:
                handler = logging.StreamHandler()
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)

        if log_file:
            log_path = Path(log_file).resolve()
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise RuntimeError(
                    f"failed to create log directory for {log_file!r}"
                ) from error

            has_file = any(
                isinstance(h, logging.FileHandler)
                and h.baseFilename == str(log_path)
                for h in self._logger.handlers
            )
            if not has_file:
                handler = logging.FileHandler(log_path)
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)

    def loglevel(self, loglevel: DMyLog) -> None:
        """Set the threshold for all destinations of this named logger."""
        self._logger.setLevel(LOG_LEVELS[loglevel])

    def info(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.info(message, extra=extra)

    def debug(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.debug(message, extra=extra)

    def warning(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.warning(message, extra=extra)

    def error(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.error(message, extra=extra)

    def critical(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.critical(message, extra=extra)
