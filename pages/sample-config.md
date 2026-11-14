---
title: Configuration and Results
author_profile: true
layout: single
---

[Homepage](/) · [Run a simulation](/pages/run-a-simulation.html)

Use [sample-config.json](/examples/sample-config.json) as a starting point. The
[JSON Schema](/snakelab/schemas/simulation-config-v2.schema.json) defines all
fields, defaults, and validation limits. Partial configurations are accepted;
the server fills in defaults before validation and storage.

The RNN remains the default. To use the Transformer with the shared 23-feature
state, submit [transformer-config.json](/examples/transformer-config.json), or
add `"type": "transformer"` and `"heads": 4` to the `model` settings. Attention
heads may be 1, 2, 4, or 8 and must divide the hidden width.

Both models support EpsilonNice safe exploration after ordinary epsilon
expires. Its defaults are `"epsilon_nice": {"probability": 0.005, "steps": 20}`.
Set the probability to zero to disable detours. See the
[feature layout and exploration behavior](/pages/architecture.html#observations-models-and-exploration).

Every valid submission creates a new run with a unique run ID, including
repeated configurations on the same project version. Earlier runs and episode
results are retained, including failed and cancelled attempts. Callers decide
whether to reuse an existing result or submit another experiment.

MariaDB stores runs in `simulation_runs` and episode measurements in
`simulation_episodes`.

For more information see the [Developer page](/pages/developer.html).
