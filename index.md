---
title: Standalone Snake Game Server
author_profile: true
layout: single
---

# Snake Game Server

- This project installs a systemd server that runs AI Snake Game simulations.
- Interactions with the server are via Zero MQ.
- State, configuration, and simulation result data are stored in MariaDb.

# Development Style

SnakeLab favors lean, clear code and fail-fast behavior. Invalid configuration,
missing dependencies, broken module contracts, and unexpected protocol data
should raise an immediate, visible error rather than trigger fallback or recovery
logic that hides the underlying defect. Defensive coverage belongs primarily in
tests and at genuine external boundaries, keeping production paths direct,
predictable, and efficient.
