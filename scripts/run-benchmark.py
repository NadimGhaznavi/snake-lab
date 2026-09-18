#!/usr/bin/env python3
"""Submit one benchmark, report throughput, and delete its persisted results."""

import argparse
import asyncio
import json
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

import pymysql

from snake_lab.control_client import AsyncLabClient, load_config
from snake_lab.protocol import METHOD_SIMULATION_STATUS


def connect_database():
    credentials = json.loads(Path(DSnakeLab.DB_CREDENTIALS_FILE).read_text())
    return pymysql.connect(
        host=DSnakeLab.DB_HOST, port=DSnakeLab.DB_PORT,
        user=DSnakeLab.DB_USER, password=credentials["password"],
        database=DSnakeLab.DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
        connect_timeout=5, read_timeout=30, write_timeout=30,
    )


def payload(response):
    if response.get("status") != "ok":
        raise RuntimeError(f"Server rejected request: {response.get('error')}")
    return response["payload"]


def measure_and_delete(connection, run_id):
    """Only delete a committed, successfully completed run, in one transaction."""
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status, TIMESTAMPDIFF(MICROSECOND, started_at, "
                "completed_at) AS elapsed_us FROM simulation_runs "
                "WHERE run_id = %s FOR UPDATE", (run_id,),
            )
            run = cursor.fetchone()
            if not run or run["status"] != "completed":
                raise RuntimeError("Benchmark has no committed completed result")
            elapsed_us = run["elapsed_us"]
            if elapsed_us is None or elapsed_us <= 0:
                raise RuntimeError("Benchmark has no positive elapsed time")
            cursor.execute(
                "SELECT COALESCE(SUM(steps), 0) AS steps "
                "FROM simulation_episodes WHERE run_id = %s", (run_id,),
            )
            steps = int(cursor.fetchone()["steps"])
            seconds = elapsed_us / 1_000_000
            print(f"Total steps: {steps:,}\nElapsed seconds: {seconds:.6f}\n"
                  f"Steps/second: {steps / seconds:,.2f}", flush=True)
            # Both configurations and simulation_episodes cascade from this row.
            cursor.execute("DELETE FROM simulation_runs WHERE run_id = %s", (run_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("Benchmark cleanup did not delete exactly one run")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    print(f"Deleted benchmark data for {run_id}.", flush=True)


async def benchmark(config):
    connection = connect_database()
    client = AsyncLabClient()
    run_id = None
    try:
        if payload(await client.active())["run"] is not None:
            raise RuntimeError("Server must be idle before starting a benchmark")
        run_id = payload(await client.submit(config))["run_id"]
        print(f"Benchmark run: {run_id}", flush=True)
        previous = None
        while True:
            status = payload(await client.request(
                METHOD_SIMULATION_STATUS, {"run_id": run_id},
            ))
            progress = (status["state"], status.get("completed_epochs", 0))
            if progress != previous:
                print(f"{progress[0]}: {progress[1]}/{status.get('epochs', '?')} episodes",
                      flush=True)
                previous = progress
            if status["state"] == "completed":
                break
            if status["state"] in {"failed", "cancelled"}:
                raise RuntimeError(f"Benchmark {status['state']}: {status.get('error', '')}")
            await asyncio.sleep(1)
        measure_and_delete(connection, run_id)
    except BaseException:
        if run_id is not None:
            print(f"Benchmark did not finish cleanly; inspect run {run_id}. "
                  "No further cleanup attempted.", file=sys.stderr)
        raise
    finally:
        client.close()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", required=True, type=Path,
                        help="Simulation JSON configuration")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this tool as root")
    try:
        asyncio.run(benchmark(load_config(args.config.expanduser())))
    except KeyboardInterrupt:
        print("Benchmark interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
