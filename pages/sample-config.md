---
title: Configuration and Results
author_profile: true
layout: single
---

[Homepage](/) · [Run a simulation](/pages/run-a-simulation.html)

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

For more information see the [Developer page](/pages/developer.html).
