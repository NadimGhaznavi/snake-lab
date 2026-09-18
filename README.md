# SnakeLab

SnakeLab is a standalone, serial AI Snake simulation server with a live Textual
client and MariaDB experiment storage.

## Install

From a release checkout on Debian Trixie:

```sh
sudo apt install python3-venv mariadb-server openssl
sudo scripts/install.sh
lab-client
```

The installer always installs the CPU PyTorch runtime. Simulation, policy
inference, and training run on CPU, including on hosts with an NVIDIA GPU.

Back up the local database with `sudo scripts/backup-db.sh`. The SQL dump is
saved in the current directory as `YYYY-MM-DD_HH:MM-snakelab-db.dump`, using
local time. An existing backup from the same minute is never overwritten.

Run a benchmark against an idle local server from this checkout:

```sh
sudo scripts/run-benchmark.py -c examples/sample-config.json
```

The script automatically uses the installed virtual environment at
`/opt/snake-lab/venv`, deriving the install directory from the credential path
in `DSnakeLab.DB_CREDENTIALS_FILE`.
The tool uses the installed credentials at `/opt/snake-lab/config/database.json`,
prints `Snake Lab Benchmark: XXX steps per second`, and calculates throughput using the run's database
start and completion timestamps (including simulation setup and persistence).
Add `-v` for episode progress, timing, and cleanup details.
Before printing the final result, it deletes only that run and its cascading episode and
configuration records. Failed or interrupted runs are retained, with their run
ID printed for inspection; interrupting the tool does not cancel the simulation.

See the [SnakeLab Homepage](https://snakelabserver.osoyalce.com) for operations,
configuration, upgrades, development, and simulation server setup.

The live client uses the legacy three-column dashboard. Game Score retains the
latest 200 received episodes in a deque, with the legacy smoothing window of
`max(1, retained_count // 40)` (five points when full). The record plot retains
the latest 500 received episodes. Loss retains all received non-null losses for
the current run and plots averaged bins of `max(1, loss_count // 75)` samples,
using the first episode in each bin, as in the legacy client. The Score Distribution
tab uses a Textual Plot histogram to count how often each score occurs across
all received episodes in the current run. Counts reset for each new run; no
plot history is fetched. Smaller terminals can scroll the dashboard.

The **Configuration** panel reads the nine LLM-tuned values for the current
run from MariaDB using a read-only transaction. It excludes fixed settings.
Database access is separate from ZMQ; use a credentials JSON file readable by
the client user, containing `password` and optionally `user` and `database`:

```sh
client/lab-client.sh --host SERVER --db-host DATABASE_HOST --db-credentials /path/to/database.json
```

Defaults use the existing local SnakeLab database settings. If the database
is unavailable, telemetry continues and the panel reports configuration as
unavailable. The client does not initialize, migrate, or update the database.
