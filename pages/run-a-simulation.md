---
title: Run a Simulation
author_profile: true
layout: single
---

[Homepage](/) · [Sample configuration](/pages/sample-config.html)

Start the installed client on the server:

```sh
lab-client
```

To run the client from another trusted host:

```sh
lab-client --host wintermute
```

Choose **Submit config**, select a JSON file, and submit it. The client displays
the live game, run progress, score, epsilon, loss, and lifecycle events.

Use **Display every X frames** to hold snapshots between board updates. Enter a
positive whole number, such as `10`, to show one in every ten received frames;
`1` displays all received frames. This client-only setting applies immediately
and does not slow the simulation. The server offers every move while a viewer
subscribes, but best-effort telemetry may drop messages.

See [Developer Integration](/pages/developer.html) to submit simulations from
another project or service.

Pause, resume, cancel, and move delay are human diagnostic controls. Move delay
ranges from 0 to 100 milliseconds in 20-millisecond steps. These controls are
not part of the experiment configuration.

## Delete simulation results

To delete the newest simulation (the highest database ID) and all its episode
results, run from a release checkout:

```sh
sudo systemctl stop snake-lab.service
sudo scripts/del-last-run.sh
sudo systemctl start snake-lab.service
```

The deletion is transactional and also works for interrupted runs. If there
are no runs, the script reports that there is nothing to delete. Keep the
server stopped until the script finishes.

To delete all runs whose high score is below 10, including their configurations
and episode results:

```sh
sudo systemctl stop snake-lab.service
sudo scripts/del-below-10.sh
sudo systemctl start snake-lab.service
```

This deletion is transactional. Runs scoring exactly 10 or higher and runs with
no recorded high score are kept.
