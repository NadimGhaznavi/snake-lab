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
