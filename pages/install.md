---
title: Installation
author_profile: true
layout: single
---

[Homepage](/) · [Architecture](/pages/architecture.html) · [Developer integration](/pages/developer.html)

## Install the server

On Debian Trixie, install the base requirements and run the installer from a
release checkout:

```sh
sudo apt install python3-venv mariadb-server openssl
sudo scripts/install.sh
```

The installer creates `/opt/prod/snakelab`, provisions the database, builds the
Python environment, and starts `snake-lab.service`. The environment always
uses the CPU PyTorch runtime.

```sh
systemctl status snake-lab.service
journalctl -u snake-lab.service -f
tail -f /opt/prod/snakelab/logs/server.log
```

Simulation, policy inference, and training run on CPU, including on hosts
with an NVIDIA GPU. No NVIDIA driver or CUDA toolkit is required.

## Start the client

```sh
lab-client
```

Connect to another trusted host with `lab-client --host SERVER`. See
[Run a simulation](/pages/run-a-simulation.html) for submitting configurations and
controlling runs.

The **Configuration** panel reads the nine LLM-tuned values for the current
run from MariaDB using a read-only transaction. It excludes fixed settings.
Database access is separate from ZMQ; use a credentials JSON file readable by
the client user, containing `password` and optionally `user` and `database`:

```sh
client/lab-client.sh --host SERVER --db-host DATABASE_HOST --db-credentials /path/to/database.json
```

Defaults use the existing local Snake Lab database settings. If the database
is unavailable, telemetry continues and the panel reports configuration as
unavailable. The client does not initialize, migrate, or update the database.

## Back up the database

Back up the local database with `sudo scripts/backup-db.sh`. The SQL dump is
saved in the current directory as `YYYY-MM-DD_HH:MM-snakelab-db.dump`, using
local time. An existing backup from the same minute is never overwritten.

## Benchmark

Run a benchmark against an idle local server from this checkout:

```sh
sudo scripts/run-benchmark.py -c examples/sample-config.json
```

The script automatically uses the installed virtual environment at
`/opt/prod/snakelab/venv`, deriving the install directory from the credential path
in `DSnakeLab.DB_CREDENTIALS_FILE`.
The tool uses the installed credentials at `/opt/prod/snakelab/config/database.json`,
prints `Snake Lab Benchmark: XXX steps per second`, and calculates throughput using the run's database
start and completion timestamps (including simulation setup and persistence).
Add `-v` for episode progress, timing, and cleanup details.
Before printing the final result, it deletes only that run and its cascading episode and
configuration records. Failed or interrupted runs are retained, with their run
ID printed for inspection; interrupting the tool does not cancel the simulation.

See [Development setup](/pages/developer.html#development-setup) to run from a source checkout.

## Upgrade

Do not upgrade while a simulation is running. From the new release checkout:

```sh
sudo scripts/upgrade.sh
```

The upgrade script stops the service, applies database schemas v1–v4,
deploys the software, and restarts the service. It rebuilds the virtual
environment when requirements change or the installation moves, and does not
provision MariaDB.

Existing `/opt/snake-lab` installations are moved to `/opt/prod/snakelab`.
Credentials and logs move with the installation; the database name, account,
and stored results stay the same. The virtual environment is rebuilt because
its launchers contain absolute paths. If rebuilding fails, the service stays
stopped; fix the reported error and rerun the upgrade. The script refuses to
migrate when both installation directories already exist.

## CMDB discovery

Register **`SnakeLab`** using CMDB’s Add Application, then run Re-Scan
Applications on the inventoried host. CMDB reads the literal version from
`/opt/prod/snakelab/snakelab/constants/DSnakeLab.py` and records the installed
release and host deployment. The name must be exactly `SnakeLab`; names with
spaces or hyphens do not meet CMDB’s discovery convention. Development
checkouts under `/opt/dev` are not discovery targets.

Python entry points are now `python -m snakelab.server` and
`python -m snakelab.client`; shared constants are in `snakelab.constants`.

Fresh installations apply the same schemas. To apply them separately while
the service is stopped, use `sudo scripts/apply-database-schema.sh`. Schema
application is safe to repeat; it does not backfill historical configuration
rows or high-score snapshots. See [Configuration queries](/pages/developer.html#configuration-queries)
for storage details and migration context.

## Uninstall

```sh
sudo scripts/uninstall.sh
```

The uninstaller removes the service, `/opt/prod/snakelab`, and the configured
MariaDB database, including all simulation history. The MariaDB user remains.
