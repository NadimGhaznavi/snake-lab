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

The simulator keeps game state, observations, policy history, actions, and
replay in device tensors. With CUDA these remain on the GPU; without CUDA the
same implementation runs on CPU. Replay sampling produces training tensors
directly, without intermediate NumPy batches. Tensor game/history layouts
include a leading environment dimension of one; concurrent sweep execution is
not implemented in this release.

The Python service still schedules episodes, handles controls, writes results,
and publishes messages. It reads a scalar terminal/exploration control flag
per move to preserve serial episode boundaries and avoid policy inference on
random exploration moves. Full game snapshots are copied to the host only
when frame telemetry is enabled; episode summaries and training loss are
read at episode boundaries. Replay window metadata is updated at episode
boundaries. This removes observation/action round trips, but does not eliminate
all CPU/GPU synchronization.

Replay capacity is allocated on the selected device at run setup. Its main
buffers use approximately `replay_max_frames * (2 * 51 * 4 + 8 + 4 + 1)` bytes,
plus training batches and indexing storage. Allocation failure fails the run;
there is no automatic switch of a CUDA run to CPU.

Food selection, exploration, and replay sampling use separately seeded device
random generators. Old releases' seeded trajectories are not preserved, and
identical results across CPU, CUDA, hardware, or library versions are not
promised. Game rules, observation ordering, terminal rewards, and serial
training cadence are retained. Parameter sweep batching remains a later phase.
