"""Command-line entry point for the SnakeLab server."""

import argparse
import asyncio
import signal

from constants.DSnakeLab import DSnakeLab
from snake_lab.database.MemorySimulationStore import MemorySimulationStore
from snake_lab.database.SimulationStore import SimulationStore
from snake_lab.database.SnakeDb import SnakeDb
from snake_lab.server.SnakeLabServer import SnakeLabServer


async def amain() -> None:
    parser = argparse.ArgumentParser(description="Run the SnakeLab server")
    parser.add_argument("--address", default="*")
    parser.add_argument("--port", type=int, default=DSnakeLab.PORT)
    parser.add_argument(
        "--telemetry-port", type=int, default=DSnakeLab.TELEMETRY_PORT
    )
    parser.add_argument(
        "--events-port", type=int, default=DSnakeLab.EVENTS_PORT
    )
    parser.add_argument("--log-file", default=DSnakeLab.SERVER_LOG_FILE)
    parser.add_argument(
        "--ephemeral",
        action="store_true",
        help="keep simulation results in memory instead of MariaDB",
    )
    args = parser.parse_args()

    store: SimulationStore
    if args.ephemeral:
        store = MemorySimulationStore()
    else:
        store = SnakeDb.connect()
        try:
            store.recover_interrupted_runs()
        except BaseException:
            store.close()
            raise

    server = SnakeLabServer(
        address=args.address,
        port=args.port,
        telemetry_port=args.telemetry_port,
        events_port=args.events_port,
        log_file=args.log_file,
        store=store,
    )

    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, server.stop)
        except (NotImplementedError, RuntimeError):
            pass
    await server.run()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
