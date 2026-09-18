#!/usr/bin/env python3
"""Run DAL tests on a disposable local MariaDB, then remove its data.

Run with: venv/bin/python scripts/run-database-tests.py
Requires mariadb-install-db and mariadbd, plus permission to open local sockets.
No installed SnakeLab database or credentials are used.
"""

import os
import sys
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import pymysql


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='snake-live-dal-', dir='/tmp') as directory:
        work = Path(directory)
        data = work / 'data'
        initialized = subprocess.run([
            '/usr/bin/mariadb-install-db', '--no-defaults', f'--datadir={data}',
            '--auth-root-authentication-method=normal', '--skip-test-db',
        ], capture_output=True, text=True)
        if initialized.returncode:
            raise RuntimeError(initialized.stdout + initialized.stderr)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        db_socket = str(work / 'db.sock')
        with (work / 'server.log').open('w') as log:
            server = subprocess.Popen([
                '/usr/sbin/mariadbd', '--no-defaults', f'--datadir={data}',
                f'--socket={db_socket}', f'--pid-file={work / "db.pid"}',
                '--bind-address=127.0.0.1', f'--port={port}', '--skip-name-resolve',
                '--innodb-buffer-pool-size=64M', '--max-connections=20',
            ], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 25
                while True:
                    try:
                        connection = pymysql.connect(unix_socket=db_socket, user='root', connect_timeout=1)
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT VERSION()')
                            print('Isolated MariaDB:', cursor.fetchone()[0], flush=True)
                        connection.close()
                        break
                    except pymysql.Error:
                        if server.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError((work / 'server.log').read_text())
                        time.sleep(0.1)
                env = dict(os.environ, SNAKELAB_TEST_DB_SOCKET=db_socket, SNAKELAB_TEST_DB_PORT=str(port))
                result = subprocess.run([
                    sys.executable, '-m', 'unittest',
                    'tests.test_database_integration', 'tests.test_database_migration',
                    'tests.test_dbmgr', 'tests.test_database', 'tests.test_benchmark', '-v',
                ], cwd=root, env=env)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
