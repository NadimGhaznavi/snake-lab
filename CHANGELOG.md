# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.1.2] - 2026-09-02 @ 17:20

### Added

- In-place upgrade tooling for deploying new releases while preserving runtime
  data.

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
