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
- MariaDB result persistence is planned; the current server keeps run state in
  memory and logs completed simulations.

# Running a Simulation

Start `lab-viewer` before submitting a simulation if you want to watch it live.
The viewer is deliberately read-only and never controls the speed of the
simulation. Use `lab-client` in a second terminal to submit the configuration
and query its authoritative run status.

For development checkouts, use `client/lab-viewer.sh` instead of the installed
launcher.

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