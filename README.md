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

The installer selects the PyTorch CUDA 12.6 runtime when `nvidia-smi` reports a
working GPU and otherwise installs the CPU runtime.

See the [SnakeLab documentation](https://snake-lab.osoyalce.com) for operation,
configuration, upgrades, development, and Wintermute setup.
