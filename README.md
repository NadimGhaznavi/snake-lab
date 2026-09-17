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

See the [SnakeLab Homepage](https://snakelabserver.osoyalce.com) for operations,
configuration, upgrades, development, and simulation server setup.

The live client uses the legacy three-column dashboard with bounded score,
record and loss plots (the latest 500 received episodes). It does not fetch
plot history. Smaller terminals can scroll the dashboard.

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
