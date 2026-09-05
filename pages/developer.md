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

Each publication is a two-part message: the UTF-8 topic followed by a JSON
envelope containing `protocol_version`, `sequence`, `run_id`, and `payload`.
Subscribe before submitting a run when the initial lifecycle events are needed.

The project's
[control client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/control_client.py)
and
[telemetry client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/telemetry_zmq.py)
are the reference implementations.
