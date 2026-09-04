---
title: SnakeLab
author_profile: true
layout: single
---

SnakeLab runs serial, configurable AI Snake simulations with PyTorch. It uses
the GPU when CUDA is available and otherwise runs on the CPU.

## Components

- A systemd simulation server.
- ZeroMQ job control on TCP port 41970.
- ZeroMQ live telemetry on TCP port 41971.
- A Textual client for submitting configurations, watching the game, and
  controlling a run.
- MariaDB storage for resolved configurations, run state, and episode results.

The ZeroMQ interfaces do not provide authentication. Expose these ports only
on a trusted network.

## Install

On Debian Trixie, install the base requirements and run the installer from a
release checkout:

```sh
sudo apt install python3-venv mariadb-server openssl
sudo scripts/install.sh
```

The installer creates `/opt/snake-lab`, provisions the database, builds the
Python environment, and starts `snake-lab.service`. If `nvidia-smi` reports a
working GPU, the environment uses the PyTorch CUDA 12.6 runtime.

```sh
systemctl status snake-lab.service
journalctl -u snake-lab.service -f
tail -f /opt/snake-lab/logs/server.log
```

See [Driver Setup](/pages/driver-setup.html) for Wintermute's NVIDIA setup.

## Run a Simulation

Start the installed client on the server:

```sh
lab-client
```

To run the client from another trusted host:

```sh
lab-client --host wintermute
```

Choose **Submit config**, select a JSON file, and submit it. The client displays
the live game, run progress, score, epsilon, loss, and lifecycle events.

See [Developer Integration](/pages/developer.html) to submit simulations from
another project or service.

Pause, resume, cancel, and move delay are human diagnostic controls. Move delay
ranges from 0 to 100 milliseconds in 20-millisecond steps. These controls are
not part of the experiment configuration.

## Configuration and Results

Use [sample-config.json](/examples/sample-config.json) as a starting point. The
[JSON Schema](/snake_lab/schemas/simulation-config-v1.schema.json) defines all
fields, defaults, and validation limits. Partial configurations are accepted;
the server fills in defaults before validation and storage.

SnakeLab treats the complete resolved configuration as a deterministic
experiment. A completed configuration runs once per project version. Repeated
submissions return the existing run, while cancelled or failed attempts restart
from the beginning.

MariaDB stores runs in `simulation_runs` and episode measurements in
`simulation_episodes`.

## Upgrade

Do not upgrade while a simulation is running. From the new release checkout:

```sh
sudo scripts/upgrade.sh
```

The upgrade script replaces the software and rebuilds the virtual environment
only when requirements change. It does not provision MariaDB or apply schema
changes.

For the one-time upgrade from a pre-0.9.0 installation, apply the initial schema
before upgrading:

```sh
sudo scripts/apply-database-schema.sh
sudo scripts/upgrade.sh
```

Database changes in future releases will include explicit release instructions.

## Development

```sh
./scripts/rebuild-venv.sh
venv/bin/python -m unittest discover -s tests
```

Run a development server without MariaDB in one terminal:

```sh
venv/bin/python -m snake_lab.server \
    --address 127.0.0.1 \
    --log-file /tmp/snake-lab.log \
    --ephemeral
```

Start the development client in another terminal:

```sh
./client/lab-client.sh
```

## Uninstall

```sh
sudo scripts/uninstall.sh
```

The uninstaller removes the service and `/opt/snake-lab`. It leaves the
MariaDB database and database user intact.

## Related Setup

- [Driver Setup](/pages/driver-setup.html): Wintermute GPU and llama.cpp build.
- [Model Setup](/pages/model-setup.html): Qwen3.5 model conversion for Fr3d.
- [Qwen3.5 4B on Hugging Face](https://huggingface.co/Qwen/Qwen3.5-4B)
