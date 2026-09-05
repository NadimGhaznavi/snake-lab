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
- ZeroMQ simulation-ended events on TCP port 41972.
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

Every valid submission creates a new run with a unique run ID, including
repeated configurations on the same project version. Earlier runs and episode
results are retained, including failed and cancelled attempts. Callers decide
whether to reuse an existing result or submit another experiment.

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

When upgrading from database schema v1 (including releases 0.9.0–0.9.2),
stop the service and apply the schema update before upgrading. This removes
the unique configuration constraint while preserving existing results. The
same command also initializes the schema for pre-0.9.0 installations:

```sh
sudo systemctl stop snake-lab.service
sudo scripts/apply-database-schema.sh
sudo scripts/upgrade.sh
```

The schema command applies v1 followed by v2 and is safe to repeat. Fresh
installations apply both automatically. Database changes in future releases
will include explicit release instructions.

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
