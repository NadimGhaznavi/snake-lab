---
title: Architecture
author_profile: true
layout: single
---

SnakeLab runs queued Snake experiments serially on CPU, stores results in
MariaDB, and streams progress to a Textual client or external subscribers.

## Components

- A systemd simulation server.
- ZeroMQ job control on TCP port 41970.
- ZeroMQ live telemetry on TCP port 41971, with per-move frames generated
  only while a viewer subscribes.
- ZeroMQ simulation-ended events on TCP port 41972.
- A Textual client for submitting configurations, watching the game, and
  controlling a run.
- MariaDB storage for resolved configurations, run state, and episode results.

## Application packages

All runtime code lives in `snake_lab/`, with shared constants in `constants/`.

| Folder | Main modules and responsibilities |
| --- | --- |
| `server/` | `SnakeLabServer` handles control requests and the FIFO run queue. `SimulationRun` holds progress; `SimulationControl` handles pause, cancellation, and delay. `Simulator` runs episodes and training. `Configuration` resolves and validates input through `JSONValidator`. |
| `game/` | `SnakeGame` owns an episode; `GameRules` applies moves to immutable `GameState`. `Position`, `Direction`, `RewardConfig`, and `StepResult` describe game values. `BoardSnapshot` converts boards for transport; `GameHelper` places food. |
| `nn/` | `RNNModel` predicts action values, `EpsilonAlgo` chooses exploration moves, `ReplayMemory` samples episode windows, and `Trainer` performs Double DQN updates. |
| `database/` | `SimulationStore` defines the server's storage contract. `SnakeDb` implements it through the generic MariaDB manager `DbMgr`; `DBHelper` maps and hashes configurations. `MemorySimulationStore` supports ephemeral runs. |
| `zmq/` | `Protocol` defines control messages; `ZMQHelper` defines completion events. `TelemetryPublisher`, `EventsPublisher`, and `TelemetrySubscriber` own transport. `TelemetryEnvelope` and `FrameTelemetry` represent live updates. |
| `client/` | `__init__.py` currently holds the Textual app and dialogs. `AsyncLabClient` sends control requests; `SnakeBoard`, `LivePlots`, and `client.tcss` provide presentation. `ConfigurationReader` reads run settings through `SnakeDb`. |
| `schemas/` | Simulation configuration v2 JSON Schema and database migrations v1–v4. The older configuration v1 schema remains in the repository. |
| `utils/` | `MyLog` provides shared logging. |

## Execution flow

1. A control request reaches `SnakeLabServer` on port **41970**. The server
   resolves the configuration, stores a new run, and queues it.
2. One worker passes the resolved configuration to `Simulator`, which combines
   game rules, policy inference, replay memory, and training on CPU.
3. Episode results go to the store and telemetry on port **41971**. Per-move
   frames are generated only while a matching viewer subscription exists.
4. The server stores the terminal result before publishing `simulation_ended`
   on port **41972**. Successful runs also save their high-score board.

`python -m snake_lab.server` starts the server; `--ephemeral` uses memory
instead of MariaDB. `python -m snake_lab.client` starts the TUI. The client
uses ZeroMQ for control and telemetry, and a separate read-only database
transaction for its configuration panel.

## Supporting folders

| Folder | Purpose |
| --- | --- |
| `constants/` | Runtime defaults, ports, version, game values, and database configuration paths. |
| `client/` | Shell launchers for the installed and development clients. |
| `scripts/` | Installation, upgrades, schema application, environment setup, backups, cleanup, benchmarks, and isolated database tests. |
| `systemd/` | Service definition for the installed server. |
| `tests/` | Unit, boundary, and integration tests, including ZeroMQ and optional MariaDB tests. |
| `examples/` | Sample simulation configuration. |
| `pages/`, `notes/` | Website documentation, images, and release notes; `index.md` is the homepage. |
| `.github/` | Repository automation. |

See [Developer integration](/pages/developer.html) for wire protocols and
runtime details, and [Coding guidelines](/pages/coding-guidelines.html) for
design conventions.
