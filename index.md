---
title: Snake Lab Server
author_profile: true
layout: single
---

![Architecture](/pages/images/architecture.png)

The Snake Lab Server operates as a Linux systemd service. It allows users to submit a simulation run configuration. The simulations are of an **AI Snake Game** run. The server houses the entire Snake Game and neural network machinary. Once it receives a valid config it starts a fixed number of simulation episodes. Simulation and simulation run data is stored in MariaDb.

This project was created to support the [Fr3d Project](https://fr3d.osoyalce.com/) which has evolved into the [Ax3l Project](https://ax3l.osoyalce.com).

## Documentation

- [Installation](/pages/install.html)
- [Architecture](/pages/architecture.html)
- [Developer integration](/pages/developer.html)
- [Control protocol](/pages/control-protocol.html)
- [Event protocol](/pages/event-protocol.html)
- [Coding guidelines](/pages/coding-guidelines.html)
- [Driver setup](/pages/driver-setup.html)
- [Model setup](/pages/model-setup.html)

## Components

- A systemd simulation server.
- ZeroMQ job control on TCP port 41970.
- ZeroMQ live telemetry on TCP port 41971, with per-move frames generated
  only while a viewer subscribes.
- ZeroMQ simulation-ended events on TCP port 41972.
- A Textual client for submitting configurations, watching the game, and
  controlling a run.
- MariaDB storage for resolved configurations, run state, and episode results.

The ZeroMQ interfaces do not provide authentication. Expose these ports only
on a trusted network.

## Install

See [Installation](/pages/install.html) for server and client setup,
database backups, and benchmarks.

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

Use **Display every X frames** to hold snapshots between board updates. Enter a
positive whole number, such as `10`, to show one in every ten received frames;
`1` displays all received frames. This client-only setting applies immediately
and does not slow the simulation. The server offers every move while a viewer
subscribes, but best-effort telemetry may drop messages.

See [Developer Integration](/pages/developer.html) to submit simulations from
another project or service.

Pause, resume, cancel, and move delay are human diagnostic controls. Move delay
ranges from 0 to 100 milliseconds in 20-millisecond steps. These controls are
not part of the experiment configuration.

## Configuration and Results

Use [sample-config.json](/examples/sample-config.json) as a starting point. The
[JSON Schema](/snake_lab/schemas/simulation-config-v2.schema.json) defines all
fields, defaults, and validation limits. Partial configurations are accepted;
the server fills in defaults before validation and storage.

Every valid submission creates a new run with a unique run ID, including
repeated configurations on the same project version. Earlier runs and episode
results are retained, including failed and cancelled attempts. Callers decide
whether to reuse an existing result or submit another experiment.

MariaDB stores runs in `simulation_runs` and episode measurements in
`simulation_episodes`.

To delete the newest simulation (the highest database ID) and all its episode
results, run from a release checkout:

```sh
sudo systemctl stop snake-lab.service
sudo scripts/del-last-run.sh
sudo systemctl start snake-lab.service
```

The deletion is transactional and also works for interrupted runs. If there
are no runs, the script reports that there is nothing to delete. Keep the
server stopped until the script finishes.

To delete all runs whose high score is below 10, including their configurations
and episode results:

```sh
sudo systemctl stop snake-lab.service
sudo scripts/del-below-10.sh
sudo systemctl start snake-lab.service
```

This deletion is transactional. Runs scoring exactly 10 or higher and runs with
no recorded high score are kept.

## Upgrade

Do not upgrade while a simulation is running. From the new release checkout:

```sh
sudo scripts/upgrade.sh
```

The upgrade script stops the service, applies database schemas v1–v4,
deploys the software, and restarts the service. It rebuilds the virtual
environment only when requirements change and does not provision MariaDB.

Fresh installations apply the same schemas. To apply them separately while
the service is stopped, use `sudo scripts/apply-database-schema.sh`. Schema
application is safe to repeat; it does not backfill historical configuration
rows or high-score snapshots. See [Configuration queries](/pages/developer.html#configuration-queries)
for storage details and migration context.

## Development

- [Architecture](/pages/architecture.html): folders, modules, and execution flow.
- [Developer integration](/pages/developer.html): protocols and runtime behavior.
- [Coding guidelines](/pages/coding-guidelines.html): component boundaries and conventions.

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

The uninstaller removes the service, `/opt/snake-lab`, and the configured
MariaDB database, including all simulation history. The MariaDB user remains.

## Related Setup

- [Driver Setup](/pages/driver-setup.html): Wintermute GPU and llama.cpp build.
- [Model Setup](/pages/model-setup.html): Qwen3.5 model conversion for Fr3d.
- [Qwen3.5 4B on Hugging Face](https://huggingface.co/Qwen/Qwen3.5-4B)
