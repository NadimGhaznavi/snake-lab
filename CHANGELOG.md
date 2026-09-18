# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

- Fix submissions and reads after MariaDB closes an idle connection. `DbMgr` reconnects once when starting a transaction reports a lost or closed connection, before application statements execute; statement and commit failures still propagate without replay. Verify idle expiry, read-only reconnection, restored session settings, and failure handling against a disposable MariaDB instance; all 55 targeted tests pass.
- Simplify database transactions by removing speculative failure-state tracking for callers that swallow errors. Let failures propagate to the transaction boundary for rollback and error translation. Remove the redundant benchmark deletion-count check after locking the unique run row, and limit rollback-error suppression to database exceptions. Retain parameter binding, transactions, and original driver error causes.

## [1.7.7] - 2026-09-18 @ 05:45

- New logo!! Last one, really.

## [1.7.6] - 2026-09-18 @ 05:38

- Made the logo background transparent.

## [1.7.5] - 2026-09-18 @ 05:34

- Remove the unrelated Fr3d driver and model setup pages and their homepage links.
- Added a snake-lab logo.
- Moved architecture image into the architecture page.

## [1.7.4] - 2026-09-18 @ 05:22

- Added architecture image onto the homepage.

## [1.7.3] - 2026-09-18 @ 05:18

- Remove `.html` suffixes from documentation links in `index.md` to use extensionless page URLs.

## [1.7.2] - 2026-09-18 @ 05:13

- Simplify the homepage to the project overview, documentation links, and components. Move run and deletion instructions to `pages/run-a-simulation.md`, configuration details to `pages/sample-config.md`, upgrade and uninstall instructions to the installation guide, and development setup to the developer guide. Update links to the relocated sections.

## [1.7.1] - 2026-09-18 @ 04:59

- Fix the manual Pages rebuild workflow to call the GitHub Pages build API with `pages: write` permission. Remove checkout and empty commits, correct the manual trigger syntax, and report build submission separately from deployment completion.

## [1.7.0] - 2026-09-18 @ 04:52

- Add a concise architecture overview covering folders, modules, and simulation execution flow.
- Move installation, client setup, backup, and benchmark instructions into `pages/install.md`; keep the README brief and link every documentation page from the homepage. Preserve dashboard details in the developer guide.
- Align documentation with current training defaults, configuration boundaries, event validation, telemetry delivery, database storage, and upgrade behavior. Clarify that GPU and model setup notes belong to the separate Fr3d setup. Verify local documentation links and Python/JSON examples.

## [1.6.8] - 2026-09-18 @ 04:32

- Restore RNN per-timestep action outputs and Trainer final-timestep selection, retaining compact [B] replay supervision and reusable sampling buffers.

## [1.6.7] - 2026-09-18 @ 04:28

- Apply the RNN output layer only to the final hidden state, returning [B,A] action values. Remove Trainer timestep slicing and verify output and gradient equivalence with the previous final-timestep calculation.

- Preallocate replay sampling buffers and return final-transition actions, rewards, and dones as [B] arrays. Update Trainer to consume them directly; document batch buffer reuse and test simulator episode continuity.
- Store completed replay episodes in one contiguous array of N + 1 observations, sharing current/next-state storage and preserving the terminal observation. Nearly halve replay state storage for long episodes.
- Cache the replay-window index when episodes complete, after eviction, so sampling no longer scans stored episodes. Preserve uniform window sampling and seeded ordering.

## [1.6.6] - 2026-09-18 @ 03:55

- Separate trusted outgoing event construction from incoming validation in `ZMQHelper`; retain payload snapshots and validate incoming events in `parse_event()`. Remove the redundant internal frame type check.
- Propagate unexpected telemetry task failures after closing the publisher, while suppressing expected task cancellation. Ensure server socket, context, and database cleanup still runs when publisher cleanup fails.
- Document and test the existing best-effort telemetry policy: overflow drops the oldest queued message regardless of topic, and shutdown discards pending delivery. Add subscriber decoding and context-ownership tests, plus publisher/server failure-cleanup coverage. All 51 targeted tests passed, including live ZeroMQ subscription tests.

## [1.6.5] - 2026-09-18 @ 03:51

- Clean up `MyLog` documentation and typing. Normalize log filenames before handler reuse, remove defensive attribute lookup, and let the named logger control thresholds so level changes reach both file and console destinations.
- Move process-wide logging shutdown from `MyLog`/`SnakeLabServer` into the server command entry point, including failure cleanup. Stopping an embedded server no longer closes unrelated logging handlers.
- Add eight logging tests covering equivalent paths, console reuse, propagation, level changes, directory failures, and shutdown ownership. All 35 targeted logging, server, simulator, and runtime-control tests passed.

## [1.6.4] - 2026-09-18 @ 03:47

- Have `Simulator` consume the server-resolved configuration directly and remove redundant component-initialization checks. Keep a private configuration copy and preserve external-input validation.
- Move shared move-delay limits into `constants/DSnakeLab.py`, removing the client dependency on `server/SimulationControl.py`.
- Update simulator and server test setup to supply resolved configurations. Repair four outdated simulator fixtures using the fixed 20×20 board and supported model/training settings; verify telemetry using actual episode lengths and retain the short-episode replay policy. All 41 targeted simulator, server, runtime-control, client, and configuration-boundary tests passed. Preserve production worker exception handling and existing cancellation behavior.

## [1.6.3] - 2026-09-18 @ 03:34

- Remove unused loss-history accumulation and `get_average_loss()` from `Trainer`; continue returning each training loss directly to the simulator.
- Add five training tests covering Double DQN action selection and target evaluation, terminal-state masking, target-network updates after optimization, independent target weights, and skipping updates when no replay batch is available. All 21 NN tests passed; retain the existing replay sampling policy.

## [1.6.2] - 2026-09-18 @ 03:27

- Complete the game package cleanup: move `Action` and `Outcome` into `constants/DGame.py`, extract `Position`, `Direction`, `RewardConfig`, and `StepResult` into their own modules, and place shared food-placement logic in `game/GameHelper.py`. Reduce `game/__init__.py` to its package description and update imports and deployment references.
- Remove the game package's dependency on the messaging layer. Board snapshot parsing now raises `BoardSnapshotError`; `FrameTelemetry` translates it into the existing `invalid_telemetry` protocol error. Preserve game mechanics, wire formats, and existing constructor validation.
- Add game boundary tests for error translation, dependency direction, and telemetry round-tripping. All 96 targeted game, messaging, client, server, and persistence regression tests passed.
- Clarify coding guidelines: trust internal module contracts through annotations and tests, validate external inputs at their boundaries, and fix programming errors at their source instead of adding defensive runtime checks or hiding failures. Preserve resource cleanup and transaction rollback while propagating errors.

## [1.6.1] - 2026-09-18 @ 03:13

- Make database statement failures consistently raise `DatabaseError` and prevent failed transactions from committing, even when a caller catches the statement error. Reject further operations until the transaction rolls back.
- Deep-copy configurations in `MemorySimulationStore` so later caller changes cannot alter stored values or invalidate their saved hashes.
- Route benchmark measurement and cleanup through `SnakeDb`. Add generic aggregation and explicit-transaction row locking to `DbMgr`, preserving atomic measurement and scoped cascading deletion. Report benchmark success only after cleanup commits.
- Move configuration column mappings into `constants/DSQL.py`, shared persistence helpers into `database/DBHelper.py`, and storage interfaces and implementations into `SimulationStore.py` and `MemorySimulationStore.py`. Leave `database/__init__.py` as a minimal package initializer and update imports and deployment checks.
- Add 11 live DAL integration tests and `scripts/run-database-tests.py`, which provisions and cleans up an isolated MariaDB instance. Verify lifecycle persistence, recovery, fresh reads, rollback, read-only enforcement, restricted client credentials, row locking, and benchmark cleanup. All 49 database and benchmark tests passed against MariaDB 11.8.6 with no skips.

## [1.6.0] - 2026-09-18 @ 02:50

- Reorganize runtime code into `nn`, `game`, `server`, `client`, `zmq`, `database`, and `utils` packages, with major classes in individually named modules. Separate game state, rules, environment, and board snapshots; group client widgets and stylesheets; and extract server, simulation, and messaging components.
- Introduce a shared database access layer: application-independent `DbMgr` owns MariaDB connections, cursors, parameterized CRUD operations, transactions, and error handling; `SnakeDb` translates application operations into database calls. Route server persistence and client configuration lookups through this layer, keeping interrupted-run recovery explicit at server startup.
- Separate configuration processing into the public `Configuration` interface and its internal `JSONValidator` helper. Keep SnakeLab validation rules and schema selection in `Configuration`, with generic defaults and JSON Schema validation in the helper.
- Update imports, tests, documentation references, and deployment copying for the new package layout. Preserve the `python -m snake_lab.server` and `python -m snake_lab.client` entry points.
- Add coding guidelines covering module ownership, layered interfaces, shared database access, and incremental refactoring, plus tests for database transactions and configuration boundaries.

## [1.5.9] - 2026-09-18 @ 00:53

- Reduced the *Torch Threads* from 10 to 5 after benchmarking. This is one less than the number of physical cores on the benchmarked (and prod) machine.

## [1.5.7] - 2026-09-18 @ 00:13

- Print a single throughput line by default for benchmarks; add `-v` for progress, timing, and cleanup details.

## [1.5.6] - 2026-09-18 @ 00:03

## [1.5.5] - 2026-09-17 @ 23:58

- Keep a single Python benchmark script that automatically uses the installed virtual environment, deriving its location from the credential-path constant.

## [1.5.4] - 2026-09-17 @ 23:52

- Include actual PyTorch intra-op and inter-op thread counts in the simulation startup log.

- Add a root-run benchmark tool that submits a JSON config, reports steps per second from persisted results, and deletes the completed benchmark's database records.

## [1.5.3] - 2026-09-17 @ 22:15

- Retain loss data for the whole observed run and thin the Loss plot using the legacy average-binning settings (75-point target), instead of a sliding window.

## [1.5.2] - 2026-09-17 @ 17:59

- Match the Score Distribution histogram bars to the snake body colour (`#025b02`).

## [1.5.1] - 2026-09-17 @ 17:44

- Restore the legacy Game Score settings: a 200-episode deque and adaptive averaging with divisor 40.

## [1.5.0] - 2026-09-17 @ 17:40

- Add a Textual Plot Score Distribution histogram to the live client, counting scores across all received episodes of the current run and resetting on run changes.

## [1.4.0] - 2026-09-17 @ 17:21

- Adapt the live client to the legacy dashboard layout and colours, with bounded score/highscore/loss plots using textual-plot 0.10.1, richer episode telemetry, and a read-only database display of the nine LLM-tuned configuration values. Preserve submission and runtime controls without changing the server protocol or fetching plot history.

## [1.3.0] - 2026-09-16 @ 18:51

- Remove server-side telemetry frame sampling and the `--telemetry-frame-rate` option. Queue every generated board frame for subscribed viewers; client display filtering remains available.

## [1.2.3] - 2026-09-16 @ 18:43

- Accept highscore board frames arriving after their score update, reuse cached record boards, and keep the Run panel score aligned with the displayed board in highscore mode.
- Show “Not Available” in the board subtitle and log a dropped-frames message once per missing highscore board.

## [1.2.2] - 2026-09-16 @ 18:20

- Compare lab-client highscores across the entire simulation run, holding the board between episodes and clearing it when a new run starts.

## [1.2.1] - 2026-09-16 @ 18:15

- Change the lab-client “Show only highscores” mode to clear the board on each new episode and refresh immediately when received frames show an improvement in that episode’s score.

## [1.2.0] - 2026-09-16 @ 18:05

- Add a lab-client “Show only highscores” checkbox that holds matching record-episode boards and disables frame-display sampling while checked.
- Shrink lab-client controls: size Submit Config to its label with two characters of padding per side, and set Pause and Cancel to 16 characters wide.

## [1.1.3] - 2026-09-15 @ 06:00

- Add a lab client control to display every X received frames, holding board snapshots between updates without slowing the simulation.

## [1.1.2] - 2026-09-15 @ 04:45

## [1.1.1] - 2026-09-13 @ 19:48

## [1.1.0] - 2026-09-13 @ 19:19

- Document high-score snapshot capture, ZMQ requests, response fields, Python client usage, and missing-snapshot handling for older runs in the developer integration guide.

- Add `simulation.highscore_snapshot` over ZMQ and an async client helper to retrieve persisted boards by run ID, including historical runs. Return explicit errors for unknown runs and unavailable snapshots; clients handle rendering and export.

- Capture the first board achieving each completed simulation’s high score, retaining immutable state references during episodes and saving the winner with final results. Capture works without telemetry subscribers and includes zero-score runs.

- Add nullable `simulation_runs.high_score_snapshot` JSON storage for one high-score board per simulation. Include the schema change in installation.

## [1.0.6] - 2026-09-13 @ 16:35

- `scripts/new-release.sh` now takes only a version and message, automatically creating the next `feat/maint-x.y.z` branch with the release patch number incremented by one.
- Uninstall now drops the configured SnakeLab database, including all simulation history, before removing installation files.

## [1.0.5] - 2026-09-13 @ 15:57

- Remove the redundant `simulation_runs.config` JSON column and write configuration values only to `configurations`. Requires a clean database reinstall and the matching AX3L reader update.

## [1.0.4] - 2026-09-13 @ 11:13

- Removed the `const` restriction on the number of epochs
- Changed default number of epochs to 500

## [1.0.3] - 2026-09-12 @ 16:33

- Increaed epochs back to 1500

## [1.0.2] - 2026-09-12 @ 14:45

- Reduced number of epochs to 500

## [1.0.0] - 2026-09-12 @ 04:05

### Changed

- Moved the PyTorch CPU thread count to `DSnakeLab.PYTORCH_NUM_THREADS` in
  `constants/DSnakeLab.py`, retaining the default of 10 threads.
- Batch size is now divisible by 2 not 8.

## [0.14.7] - 2026-09-09 @ 21:40

## [0.14.6] - 2026-09-09 @ 21:37

### Added

- `scripts/del-below-10.sh` deletes runs with high scores below 10 and their
  configurations and episode results in one transaction.

## [0.14.5] - 2026-09-09 @ 18:27

- Reduced training batch_size and sequence_length

## [0.14.4] - 2026-09-09 @ 17:36

- Reduced max model.hidden_size

## [0.14.3] - 2026-09-09 @ 17:03

### Added

- Simple database backup script: `sudo scripts/backup-db.sh` writes a timestamped
  SnakeLab SQL dump to the current directory.

## [0.14.2] - 2026-09-09 @ 06:09

### Changed

- Allow any nonnegative integer seed in simulation configuration schema v2,
  replacing the fixed seed list while retaining the default of 1970. This allows
  Fr3d's seed rotation to submit consecutive seeds such as 1971 and 1972.

## [0.14.1] - 2026-09-08 @ 21:48

### Changed

- Made the granularity of the allowed model hidden size from 32 to 16

## [0.14.0] - 2026-09-08 @ 19:23

### Changed

- Use simulation configuration schema v2 for server validation and fresh installs,
  with 1500 epochs, updated runtime defaults, and bounded parameter ranges.
- Update schema links and database test configurations for v2. PROD deployment
  uses a clean uninstall, database drop, and reinstall; no data migration is needed.

## [0.13.1] - 2026-09-07 @ 21:31

- The simulation configuration schema now defines a finite, bounded experimental 
  search space using fixed values, enums, and constrained parameter ranges.
- Updated sample config based on the new schema

## [0.13.0] - 2026-09-07 @ 17:10

### Added

- Architecture diagram on the website homepage.
- Queryable `configurations` table with all 26 runtime configuration values,
  linked to each run and written atomically with run creation.
- Database schema v3 creates the configurations table; install and upgrade
  apply it before starting the service. Release 0.13.0 uses a clean database
  reinstall instead of migrating historical configurations.

### Removed

- Unused `x-snakelab-sweepable` annotations from the configuration schema.


### One-time v0.13.0 setup

Run from the release checkout to start with an empty database. Uninstall
deletes the database and all existing simulation history.

```bash
sudo scripts/uninstall.sh
sudo scripts/install.sh
```

## [0.12.0] - 2026-09-07 @ 14:10

### Changed

- Increased the default training learning rate from 0.002 to 0.0021.
- Updated the README documentation link to `snakelabserver.osoyalce.com`
  and described the setup guide as simulation server setup.

## [0.11.2] - 2026-09-07 @ 07:13

### Changed

- Website formatting only: added a trailing blank line to the home page.

## [0.11.1] - 2026-09-07 @ 07:09

### Changed

- Rewrote the website introduction to describe the simulation service,
  MariaDB persistence, and its relationship to the Fr3d project.
- Changed the documentation site's custom domain to
  `snakelabserver.osoyalce.com`.

## [0.11.0] - 2026-09-06 @ 12:38

### Changed

- Updated release metadata to 0.11.0. This tag contains no application changes.

## [0.10.11] - 2026-09-06 @ 11:26

### Added

- Include the running project version in the health response so Fr3d can
  initialize learning-rate experiments after a SnakeLab release change.

## [0.10.10] - 2026-09-06 @ 10:50

### Added

- Added `scripts/del-last-run.sh` to transactionally delete the newest
  simulation run and its episode results, including interrupted runs.
  Documented stopping the service before deletion and restarting it afterward.

## [0.10.9] - 2026-09-06 @ 10:19

### Changed

- Explicitly configure PyTorch to use 10 CPU threads for simulations instead of
  relying on its default thread count.

## [0.10.8] - 2026-09-05 @ 07:52

### Fixed

- Completed the replay/trainer rollback: sample fixed-length sliding windows
  uniformly without replacement and train on the final move of each window.
  Removed terminal-aligned chunk storage and whole-game, all-moves training.
- Restored the default batch size of 64 sequences and removed
  `replay_min_episodes`; sampling starts when enough complete windows exist.
  Kept the sequence-length default of 8 and CPU-only execution.

## [0.10.7] - 2026-09-05 @ 07:44

### Changed

- Updated release metadata to 0.10.7. This tag contains no application changes.

## [0.10.6] - 2026-09-05 @ 07:40

### Changed

- Increased the default recurrent sequence length from 4 to 8 frames.

## [0.10.4] - 2026-09-05 @ 07:21

### Changed

- Default training batch size is now 1 game. Added configurable
  `training.replay_min_episodes` (default 30); sampling waits until enough
  eligible completed games are currently retained in replay.
- Replay discards games shorter than `sequence_length` and drops incomplete
  prefixes from longer games, retaining non-overlapping chunks aligned to the
  terminal move. Chunks are built when append receives the terminal transition.
- Training samples games uniformly without replacement and learns from every
  move in every retained chunk in one optimizer update. A single-game batch
  reuses stored NumPy arrays without batch-time reshaping or copying. Explicit
  batch sizes now count games, so saved configurations should be reviewed.

## [0.10.3] - 2026-09-05 @ 06:40

### Changed

- Reverted the 0.10.2 tensor game and replay rewrite after observed simulation
  slowdowns. Restored the Python game rules, exploration, and NumPy replay path.
- Forced policy inference and training to CPU even on CUDA-capable hosts.
  Subscription-driven telemetry, telemetry state logging, and completion
  events are retained.
- Installation and environment rebuilds now always use CPU PyTorch. The changed
  CPU requirements file triggers an environment rebuild during upgrade from
  earlier releases. Seeded trajectories differ from the 0.10.2 tensor backend.

## [0.10.2] - 2026-09-05 @ 06:24

### Changed

- Moved simulation game state, observations, rolling policy history, actions,
  exploration draws, and replay storage to device tensors. CUDA hosts now run
  the numerical game rules and replay sampling on the GPU; CPU hosts use the
  same tensor implementation. Episodes remain serial with one training attempt
  after each completed episode.
- Preallocated replay buffers retain complete episodes and produce tensor
  batches directly for training. Host synchronization remains for per-move
  terminal/exploration control flags, episode results, and subscribed telemetry.
- Tensor random generators replace Python random streams for food, exploration,
  and replay sampling. Seeded trajectories differ from earlier releases;
  cross-device bitwise reproducibility is not guaranteed.

## [0.10.1] - 2026-09-05 @ 05:37

### Added

- Log whether per-move telemetry is enabled or disabled on the first move of
  each simulation run, then only when that state changes.

## [0.10.0] - 2026-09-05 @ 05:28

### Added

- Demand-driven per-move telemetry: frame construction and publication stop
  when no subscription matches `snake_lab.frame`, and resume when a viewer
  subscribes during a run. Run/episode telemetry and completion events remain
  independent. Existing clients, ports, and message formats are compatible.

### Changed

- Event protocol v2 adds explicit `event_type` and moves `run_id` into
  `payload`. Event subscribers must update their version check and field access;
  control and telemetry remain on protocol v1. Topics and ports are unchanged.
- Replaced `offer_simulation_ended()` with validated
  `publish_event(event_type, payload)` and added transport-independent event
  definitions and parsing in `event_protocol.py`.
- Split developer documentation into a concise integration overview and
  dedicated control and event protocol references.

## [0.9.3] - 2026-09-04 @ 23:49

### Added

- A dedicated ZeroMQ events publisher on port 41972, configurable with
  `--events-port`, broadcasting `snake_lab.simulation.ended` after a run's
  completed, failed, or cancelled state is stored. Pending events are sent
  before the publisher closes during orderly shutdown.

### Changed

- Every valid simulation submission now creates a new queued run, including
  repeated configurations on the same project version. Prior runs and episode
  results are preserved; callers control duplicate detection and result reuse.
- Added database schema v2 to remove the unique configuration constraint.
  Existing installations must stop `snake-lab.service`, run
  `sudo scripts/apply-database-schema.sh`, and then run
  `sudo scripts/upgrade.sh`. Fresh installations apply the migration
  automatically.

## [0.9.2] - 2026-09-04 @ 23:16

### Changed

- Extended the TUI title widget across the full terminal width.

## [0.9.1] - 2026-09-04 @ 19:47

### Added

- Added a cross-project developer guide with the ZeroMQ request contract, a
  self-contained asynchronous submission client, response examples, and live
  telemetry details.

### Changed

- Reworked the project documentation into a concise installation, operation,
  configuration, upgrade, and development reference.
- Distinguished SnakeLab's PyTorch CUDA runtime from the local CUDA toolkit and
  Qwen/llama.cpp setup used by the future Fr3d integration.

## [0.9.0] - 2026-09-04 @ 19:27

### Added

- Transactional MariaDB persistence for resolved simulation configurations,
  run lifecycle state, and per-episode results.
- Deterministic duplicate detection keyed by project version and the SHA-256
  hash of the complete resolved configuration, while allowing an incomplete
  cancelled or failed attempt to be restarted in place.
- A versioned initial database schema and an explicit
  `scripts/apply-database-schema.sh` command for existing installations.

### Changed

- Store the SnakeLab project version with every simulation run so identical
  configurations can be evaluated again after the simulation software changes.
- Keep database provisioning and schema application in fresh installation and
  explicit database-maintenance paths; `upgrade.sh` no longer accesses MariaDB.
- Treat MariaDB as a required runtime dependency and terminate the service if
  its single simulation worker fails, allowing systemd to restart it cleanly.

## [0.8.3] - 2026-09-04 @ 18:46

### Changed

- Limited the human diagnostic move-delay control to 0–100 milliseconds in
  20-millisecond steps.

## [0.8.2] - 2026-09-04 @ 18:41

### Changed

- Moved Events into a full-width panel beneath the game and sidebar.
  Aligned Control and Run within the board's 22-row height.

## [0.8.1] - 2026-09-04 @ 18:31

### Changed

- Fixed the game panel at its natural 20-by-20 board size, placed Events
  beneath it, and let the Control and Run sidebar fill the remaining width.

## [0.8.0] - 2026-09-04 @ 18:24

### Added

- Local JSON configuration loading and submission from `lab-client` through
  the existing simulation submission API.

### Changed

- Promoted the Textual viewer to the single human-facing `lab-client`
  application.

### Removed

- The menu-driven administrative client, non-interactive `-c` mode, and the
  separate `lab-viewer` command.

## [0.7.5] - 2026-09-04 @ 17:23

### Changed

- Made pause, cancel, and cancellation-confirmation buttons compact and
  reduced the viewer's control-button row to one terminal line.

## [0.7.4] - 2026-09-04 @ 05:48

### Added

- Non-interactive `lab-client -c <config.json>` submission with JSON output
  and process status suitable for shell automation.

### Changed

- Moved and compacted the viewer controls so they remain visible in standard
  24-row terminals.

## [0.7.3] - 2026-09-04 @ 05:38

### Added

- Human-only pause, resume, cancellation, and move-delay controls in
  `lab-viewer`, including active-run discovery and cancellation confirmation.
- Cooperative per-run runtime control that leaves reproducible experiment
  configuration unchanged and allows the serial worker to continue after a
  cancelled run.

### Changed

- Preserve every game frame when a nonzero diagnostic move delay is active;
  full-speed simulations continue to use rate-limited latest-frame telemetry.

## [0.7.2] - 2026-09-04 @ 05:10

### Changed

- Reduced the sample configuration from 1,500 to 100 episodes for faster runs.

## [0.7.1] - 2026-09-04 @ 05:05

### Changed

- Added Fr3d artwork as the website logo and replaced the images in the
  driver and model setup guides.

## [0.7.0] - 2026-09-04 @ 04:38

### Added

- Live ZeroMQ PUB/SUB telemetry for run lifecycle, complete episodes, and
  rate-limited latest-frame board snapshots on port 41971.
- A stripped-down `lab-viewer` Textual interface with a flicker-free live
  Snake board, run status, training state, and event display.

### Changed

- Decoupled display frame rate from simulation speed so attaching a viewer
  never adds a move delay to the simulation hot loop.

## [0.6.0] - 2026-09-04 @ 03:32

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

### Fixed

- Enabled simulator console logging so runtime messages also appear in the
  systemd journal.

## [0.4.1] - 2026-09-03 @ 04:23

### Added

- Simulator logging to the shared server log with a distinct component name.

### Changed

- Passed the server's configured log destination to the simulator and removed
  the duplicate startup message printed outside the logger.

## [0.4.0] - 2026-09-03 @ 04:09

### Added

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

## [0.1.3] - 2026-09-02 @ 17:22

### Removed

- Removed the post-restart ZeroMQ health check from installation and upgrade
  scripts.

## [0.1.2] - 2026-09-02 @ 17:20

### Added

- In-place upgrade tooling with a post-restart ZeroMQ health check.

### Changed

- Separate replaceable application files under `/opt/snake-lab/app` from the
  persistent `venv/` and `logs/` directories.
- Rebuild the production virtual environment during an upgrade only when
  `requirements.txt` changes.

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
