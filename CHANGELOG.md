# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Deterministic epsilon-greedy exploration with episode-based decay,
  configurable floor and cutoff, and injection counters.
- Native deterministic Snake environment with immutable game snapshots,
  relative actions, egocentric observations, configurable rewards, and
  explicit terminal outcomes.
- Game-mechanics tests covering movement, collisions, food, board completion,
  observation rotation, move budgets, and seeded reproducibility.
- Fixed-shape, episode-aware replay memory that produces dense NumPy batches
  for recurrent training without crossing episode boundaries.
- Native recurrent model and Double DQN trainer with batched sequence training,
  target-network updates, and CPU/GPU device support.

### Changed

- Replaced the threaded simulation worker with a single asyncio FIFO worker
  and made the simulator an async, cooperatively yielding task.
- Expanded the external JSON Schema into the authoritative source for game,
  reward, model, replay, trainer, epsilon, and random-seed configuration.
- Added the complete serial simulation loop with independent deterministic
  episode seeds, rolling recurrent policy windows, and run/episode results.
- Changed recurrent Double DQN training to calculate loss from the final frame
  of each sampled sequence while retaining earlier frames as temporal context.
- Added live simulation progress and last-episode details to status responses,
  plus a simulation-status option in the administrative CLI.

## [0.4.2] - 2026-09-03 @ 04:25

## [0.4.1] - 2026-09-03 @ 04:23

## [0.4.0] - 2026-09-03 @ 04:09

### Added

- Simulator logging to the shared server log with a distinct component name.
- Versioned JSON Schema simulation configuration template with external
  defaults, validation constraints, and descriptive metadata.
- Configuration management that resolves submitted overrides into complete,
  validated runtime configurations.

## [0.3.0] - 2026-09-03 @ 03:15

### Added

- Initial PyTorch simulator runtime probe that executes a tensor operation and
  reports whether it ran on the CPU or an identified CUDA GPU.
- Hardware-aware PyTorch environment installation using a CPU wheel on
  development hosts and a CUDA 12.6 wheel on NVIDIA GPU hosts.

### Fixed

- Preserve the caller's working directory in client launchers so relative
  configuration paths resolve from where `lab-client` was invoked.

## [0.2.0] - 2026-09-02 @ 17:58

### Added

- MariaDB connection constants and installer provisioning for a dedicated
  `snakelab` database and local `snakelab` database user.
- Generated database credentials stored outside the application tree at
  `/opt/snake-lab/config/database.json`.
- Versioned ZeroMQ JSON messaging for simulation submission and status queries.
- Strict validation for the initial simulation configuration schema.
- FIFO simulation queue with stub execution and result persistence.
- Administrative client support for submitting JSON configuration files.
- Sample simulation configuration under `examples/`.

## [0.1.4] - 2026-09-02 @ 17:26

### Added

- In-place `upgrade.sh` tooling and shared deployment functions used by both
  fresh installations and upgrades.

### Changed

- Split replaceable application code under `/opt/snake-lab/app` from persistent
  `venv/` and `logs/` directories.
- Preserve the production virtual environment during upgrades, rebuilding it
  only when `requirements.txt` changes.
- Remove obsolete flat-layout application directories during migration.
- Update the systemd working directory and installed client launcher for the
  new application layout.

### Fixed

- Set service-readable permissions on staged application directories before
  promotion, preventing systemd `status=200/CHDIR` startup failures.

## [0.1.1] - 2026-09-02 @ 17:13

### Added

- Persistent server logging under `/opt/snake-lab/logs`.

### Changed

- Run the systemd service as a dedicated `snake-lab` system account with write
  access limited to its log directory.

## [0.1.0] - 2026-09-02 @ 16:44

### Added

- Unit and process-level ZeroMQ integration tests for health and unknown-message
  responses.

### Changed

- Refactored the administrative client into the canonical `snake_lab.client`
  module with its launcher under `client/`.
- Consolidated installation lifecycle tooling under `scripts/`.
- Standardized development and production virtual environments on the `venv/`
  directory name.
- Updated the installed layout and systemd service paths for
  `/opt/snake-lab`.
- Simplified runtime error handling to fail immediately on dependency,
  transport, and protocol errors.

### Removed

## [0.0.1] - 2026-09-02 @ 15:51

### Added

- Initial standalone Snake Game server project documentation.
- Project version and logging constants.
- Shared logging utility.
- Automated feature-to-release workflow for updating the project version and
  changelog, merging through `dev` and `main`, tagging, and publishing releases.
- ZeroMQ request/reply server listening on port 41970 with a `health` message.
- Interactive `lab-client` with health-check and quit menu options.
- Installation, uninstallation, virtual-environment rebuild, and systemd service
  tooling for deployments under `/opt/snake-lab`.

### Changed

### Removed
