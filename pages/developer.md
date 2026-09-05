---
title: Developer Integration
author_profile: true
layout: single
---

SnakeLab exposes three ZeroMQ interfaces for downstream systems. Install
`pyzmq` for Python clients and replace `wintermute` with your server hostname.

| Interface | Default endpoint | Client socket | Reference |
| --- | --- | --- | --- |
| Control | `tcp://wintermute:41970` | `REQ` | [Control protocol](/pages/control-protocol.html) |
| Events | `tcp://wintermute:41972` | `SUB` | [Event protocol](/pages/event-protocol.html) |
| Telemetry | `tcp://wintermute:41971` | `SUB` | [Live telemetry](#live-telemetry) |

1. Establish an event subscription before submitting work.
2. Call `simulation.submit` on the control port with a configuration object.
3. Save the returned `run_id`; the reply confirms the run is queued.
4. React to `simulation_ended` events whose `payload.run_id` matches that run.

The event is an asynchronous completion result. Delivery is best effort, with
no acknowledgement or replay; use `simulation.status` to reconcile missed
notifications while the run is known to the server. Every submission creates
a new run, including retries after a timeout.

Control and telemetry use protocol version 1. Events use their independently
versioned protocol, currently version 2.

## Live Telemetry

Live telemetry is published on `tcp://wintermute:41971`. Connect a ZeroMQ `SUB`
socket and subscribe to one or more topics:

- `snake_lab.run`
- `snake_lab.episode`
- `snake_lab.frame`

Per-move frames are built and published only while a subscription matches
`snake_lab.frame`. Opening `lab-client` during a run enables streaming on
subsequent moves; closing the last viewer disables it once ZeroMQ reports the
disconnection. Prefix subscriptions such as `snake_lab.` and the empty filter
(all topics) also enable frames. Subscribing only to run, episode, or completion
events does not enable them. Subscription and disconnect detection are
asynchronous; joining a paused run provides a fresh frame on its next move.
Run/episode telemetry, stored results, and completion events continue independently.
No client change or simulation configuration option is required.

Each publication is a two-part message: the UTF-8 topic followed by a JSON
envelope containing `protocol_version`, `sequence`, `run_id`, and `payload`.
Subscribe before submitting a run when the initial lifecycle events are needed.

The project's
[control client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/control_client.py)
and
[telemetry client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/telemetry_zmq.py)
are the reference implementations.

## Simulation Execution

Game logic, policy inference, replay storage, and training run on CPU. The
simulator uses the original Python game rules, Python exploration generator,
and NumPy replay batches. Episodes remain serial with one training attempt
after each completed episode when a batch is available. CUDA availability does
not change the selected device.

This restores the execution path used before 0.10.2, with inference and
training now forced to CPU. Seeded trajectories differ from the tensor-based
0.10.2 release; identical results across hardware or library versions are not
guaranteed. Subscription-driven telemetry and completion event semantics are
unchanged.

## Replay and Training

Replay stores complete episodes and samples fixed-length sliding windows
uniformly across all eligible windows, without replacement within a batch.
Windows never cross episode boundaries. Longer games contribute more windows;
a batch can contain multiple windows from the same game.

The defaults are `training.batch_size: 64` (windows) and
`training.sequence_length: 8` (moves). Training starts when enough windows
exist for a batch; there is no minimum episode count. Each sampled window
contributes its final move as the loss target. Terminal moves are included
when their ending windows are selected.

The whole-game sampling and terminal-aligned chunking introduced in 0.10.4
have been rolled back. Remove `training.replay_min_episodes` from saved
configurations created with that feature. Explicit `batch_size` values remain
supported and now count windows again; use 64 to match the restored default.
