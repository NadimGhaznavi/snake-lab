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

These complete 500-episode configurations use the same seed, rewards, training
settings, and ordinary epsilon schedule. They differ only in the model and
whether EpsilonNice is enabled:

| Model and exploration | Configuration |
| --- | --- |
| RNN + Epsilon | [rnn-epsilon.json](/examples/rnn-epsilon.json) |
| RNN + Epsilon + EpsilonNice | [rnn-epsilon-nice.json](/examples/rnn-epsilon-nice.json) |
| Transformer + Epsilon | [transformer-epsilon.json](/examples/transformer-epsilon.json) |
| Transformer + Epsilon + EpsilonNice | [transformer-epsilon-nice.json](/examples/transformer-epsilon-nice.json) |

Installation copies the examples to `/opt/prod/snakelab/examples/`. Start
`lab-client`, choose **Submit config**, enter a sample's full path, and choose
**Submit**. For example, enter
`/opt/prod/snakelab/examples/transformer-epsilon-nice.json`.
The dialog initially selects the bundled `sample-config.json` regardless of
the directory from which the client was launched. Paths refer to the machine
running the TUI, including when connecting to a remote simulation server.

`sample-config.json` contains the RNN + Epsilon + EpsilonNice configuration;
`transformer-config.json` contains the corresponding Transformer configuration.

The RNN remains the default. To use the Transformer with the shared 24-feature
state, submit [transformer-config.json](/examples/transformer-config.json), or
add `"type": "transformer"` and `"heads": 4` to the `model` settings. Attention
heads may be 1, 2, 4, or 8 and must divide the hidden width.

Both models support EpsilonNice safe exploration after ordinary epsilon
expires. Its defaults are `"epsilon_nice": {"probability": 0.005, "steps": 20}`.
Set the probability to zero to disable detours. See the
[feature layout and exploration behavior](/pages/architecture.html#observations-models-and-exploration).

`epochs` must be a positive integer; its default is 500. With the default
ordinary epsilon schedule, EpsilonNice becomes eligible at episode 227.
The schedule starts at 0.96, decays by 0.97 after each episode, and snaps to
zero below 0.001. Nice-enabled samples use probability 0.005 and 20 detour
steps; Epsilon-only samples explicitly set the Nice probability to zero.

Reward values accept finite fractional numbers. Food and closer-to-food rewards
are non-negative; wall, body, move-limit, empty-move, and further-from-food
rewards are non-positive. Distance shaping retains its bounds of 0 to 6 and
-6 to 0. For gentler shaping, try `"closer_to_food": 0.1` and
`"further_from_food": -0.1`. A positive sum of the closer and further values
can reward loops without eating food; use balanced or net-negative pairs when
comparing learning behavior. Defaults are food `+10`, wall/body/move-limit
penalties `-10`, empty moves `0`, and balanced distance shaping `+1/-1`.

Every valid submission creates a new run with a unique run ID, including
repeated configurations on the same project version. Earlier runs and episode
results are retained, including failed and cancelled attempts. Callers decide
whether to reuse an existing result or submit another experiment.

MariaDB stores runs in `simulation_runs` and episode measurements in
`simulation_episodes`, including total reward, termination outcome, and separate
ordinary epsilon and EpsilonNice injection counts.

For more information see the [Developer page](/pages/developer.html).
