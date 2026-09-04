---
title: Standalone Snake Game Server
author_profile: true
layout: single
---

# Snake Game Server

- This project installs a systemd server that runs AI Snake Game simulations.
- Job control uses ZeroMQ REQ/REP on TCP port 41970.
- Live run, episode, and game-frame telemetry uses ZeroMQ PUB/SUB on TCP port
  41971.
- MariaDB stores the complete resolved configuration, project version, run
  lifecycle, and per-episode score, step, epsilon, and loss results.
- A configuration is run once per SnakeLab project version. Submitting the same
  resolved configuration again returns its existing run instead of duplicating
  a deterministic experiment. Cancelled and failed attempts may be explicitly
  resubmitted and restart from the beginning.

# Running a Simulation

Start `lab-client` to load and submit a local JSON configuration, then watch
the simulation live. The client remembers the last configuration path for the
next submission.

The client provides human-only pause, resume, cancellation, and move-delay
controls. Move delay ranges from 0 through 100 milliseconds in 20-millisecond
steps. Zero leaves the simulation at full speed and displays sampled telemetry;
a nonzero delay enables diagnostic mode, slowing the server between moves and
preserving every frame for visual inspection. These runtime controls remain
separate from the reproducible experiment JSON.

For development checkouts, use `client/lab-client.sh` instead of the installed
launcher.

# Database Lifecycle

Fresh installations provision MariaDB and apply the current schema. Software
upgrades deliberately do not access MariaDB. To initialize the schema on an
installation created before result persistence was introduced, explicitly run
`sudo scripts/apply-database-schema.sh` from the release checkout before
upgrading the application.

# Development Style

SnakeLab favors lean, clear code and fail-fast behavior. Invalid configuration,
missing dependencies, broken module contracts, and unexpected protocol data
should raise an immediate, visible error rather than trigger fallback or recovery
logic that hides the underlying defect. Defensive coverage belongs primarily in
tests and at genuine external boundaries, keeping production paths direct,
predictable, and efficient.

# Links

## Project

- [Driver Setup](/pages/driver-setup.html)
- [Model Setup](/pages/model-setup.html)

## External

- [Qwen3.5 4B on HuggingFace](https://huggingface.co/Qwen/Qwen3.5-4B)
- [Qwen on ReadTheDocs](https://qwen.readthedocs.io/en/latest/)
- [Qwen Homepage](https://qwen.ai)
