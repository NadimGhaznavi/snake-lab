#!/usr/bin/env python3
"""Submit one benchmark, report throughput, and delete its persisted results."""

import argparse
import asyncio
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants.DSnakeLab import DSnakeLab


if __name__ == "__main__":
    # Credentials live in <install directory>/config/database.json.
    install_dir = Path(DSnakeLab.DB_CREDENTIALS_FILE).parent.parent
    installed_venv = install_dir / "venv"
    installed_python = installed_venv / "bin/python"
    if Path(sys.prefix) != installed_venv:
        if not os.access(installed_python, os.X_OK):
            sys.exit(f"Installed Python environment not found: {installed_python}")
        os.execv(str(installed_python), [str(installed_python), str(Path(__file__).resolve()), *sys.argv[1:]])

from snake_lab.database.SnakeDb import SnakeDb

from snake_lab.client.AsyncLabClient import AsyncLabClient, load_config
from snake_lab.zmq.Protocol import METHOD_SIMULATION_STATUS


def connect_database():
    return SnakeDb.connect(connect_timeout=5, read_timeout=30, write_timeout=30)


def payload(response):
    if response.get("status") != "ok":
        raise RuntimeError(f"Server rejected request: {response.get('error')}")
    return response["payload"]


def measure_and_delete(database, run_id, verbose=False):
    """Report a benchmark after the DAL has committed its cleanup."""
    steps, seconds = database.measure_and_delete_benchmark(run_id)
    if verbose:
        print(f"Total steps: {steps:,}\nElapsed seconds: {seconds:.6f}\n"
              f"Steps/second: {steps / seconds:,.0f}", flush=True)
        print(f"Deleted benchmark data for {run_id}.", flush=True)
    print(f"Snake Lab Benchmark: {steps / seconds:.0f} steps per second", flush=True)


async def benchmark(config, verbose=False):
    database = connect_database()
    client = None
    run_id = None
    try:
        client = AsyncLabClient()
        if payload(await client.active())["run"] is not None:
            raise RuntimeError("Server must be idle before starting a benchmark")
        run_id = payload(await client.submit(config))["run_id"]
        if verbose:
            print(f"Benchmark run: {run_id}", flush=True)
        previous = None
        while True:
            status = payload(await client.request(
                METHOD_SIMULATION_STATUS, {"run_id": run_id},
            ))
            progress = (status["state"], status.get("completed_epochs", 0))
            if verbose and progress != previous:
                print(f"{progress[0]}: {progress[1]}/{status.get('epochs', '?')} episodes",
                      flush=True)
                previous = progress
            if status["state"] == "completed":
                break
            if status["state"] in {"failed", "cancelled"}:
                raise RuntimeError(f"Benchmark {status['state']}: {status.get('error', '')}")
            await asyncio.sleep(1)
        measure_and_delete(database, run_id, verbose=verbose)
    except BaseException:
        if run_id is not None:
            print(f"Benchmark did not finish cleanly; inspect run {run_id}. "
                  "No further cleanup attempted.", file=sys.stderr)
        raise
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", required=True, type=Path,
                        help="Simulation JSON configuration")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show progress, timing, and cleanup details")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this tool as root")
    try:
        asyncio.run(benchmark(load_config(args.config.expanduser()), verbose=args.verbose))
    except KeyboardInterrupt:
        print("Benchmark interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
