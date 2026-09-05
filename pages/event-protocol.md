---
title: Event Protocol
author_profile: true
layout: single
---

[Developer overview](/pages/developer.html) · [Control protocol](/pages/control-protocol.html)

## Transport and Envelope

The server publishes events on `tcp://wintermute:41972`. `--events-port`
changes the port; `--address` selects the bind address for all three interfaces.
Connect a ZeroMQ `SUB` socket and subscribe to the desired topic.
Each publication has exactly two frames: a UTF-8 topic, followed by a UTF-8
JSON object with these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `protocol_version` | integer | Event protocol version, currently `2` |
| `event_type` | string | Explicit event identifier from the table below |
| `payload` | object | Fields defined for that event type |

Event definitions and validation live in `snake_lab/event_protocol.py`.
`event_message(event_type, payload)` validates outgoing messages;
`parse_event(decoded_json)` validates incoming envelopes. Invalid messages
raise `ProtocolError` (`invalid_event`, `unknown_event`, or `unsupported_protocol`).
Unknown fields, event types, and versions are rejected by these helpers.

## Supported Event Types

| Event type | Constant | Subscription topic | Required payload | Optional payload |
| --- | --- | --- | --- | --- |
| `simulation_ended` | `EVENT_SIMULATION_ENDED` | `snake_lab.simulation.ended` | `run_id`, `state` | `error` |

### simulation_ended

Signals that a simulation reached a terminal state after its final state and
results were stored. Correlate `payload.run_id` with the `run_id` returned by
`simulation.submit`; the event does not carry the control request's `request_id`.

| Payload field | Type | Meaning |
| --- | --- | --- |
| `run_id` | non-empty string | Simulation run identifier |
| `state` | string | Exactly `completed`, `failed`, or `cancelled` |
| `error` | string, optional | Error details; omitted when absent, never null |

```json
{
  "protocol_version": 2,
  "event_type": "simulation_ended",
  "payload": {
    "run_id": "f6e72cb3-9bcf-4669-b368-a17c656bad79",
    "state": "completed"
  }
}
```

A failed run uses `state: "failed"` and the server includes its error string.
The schema permits an omitted error. Cancellation includes queued cancellations
and runs cancelled during orderly shutdown. The intermediate `cancelling`
state does not emit this event. Repeated configurations create separate runs
and completion events with distinct run identifiers.

## Subscription Example

Start this subscriber before submitting work from another client:

```python
import json
import zmq

from snake_lab.event_protocol import (
    EVENT_SIMULATION_ENDED,
    TOPIC_SIMULATION_ENDED,
    parse_event,
)

with zmq.Context() as context:
    with context.socket(zmq.SUB) as socket:
        socket.setsockopt(zmq.SUBSCRIBE, TOPIC_SIMULATION_ENDED.encode("utf-8"))
        socket.connect("tcp://wintermute:41972")
        while True:
            topic, body = socket.recv_multipart()
            if topic != TOPIC_SIMULATION_ENDED.encode("utf-8"):
                continue
            event = parse_event(json.loads(body))
            if event["event_type"] == EVENT_SIMULATION_ENDED:
                result = event["payload"]
                print(result["run_id"], result["state"], result.get("error"))
```

## Delivery and Publishing

Subscriptions take time to propagate; `connect()` returning does not establish
readiness. This is a live, best-effort stream with no acknowledgement or replay.
Disconnected, late, or slow subscribers may miss events. Use the control
`simulation.status` method to reconcile missed notifications for runs known
to the current server process. There is no ordering guarantee across the
separate control, event, and telemetry sockets.

Server code calls `EventsPublisher.publish_event(event_type, payload)`. The call
validates and snapshots the payload, then queues it for asynchronous delivery.
Returning means local enqueueing, not receipt by a subscriber. Events are
processed individually in queue order. Orderly shutdown drains pending events
before closing the publisher when the transport remains operational; this
does not guarantee delivery.

## Migration from Event Version 1

Event version 2 replaces the former envelope's top-level `run_id` with
`event_type` and moves `run_id` into `payload`. Update subscribers to check
version 2, dispatch on `event_type`, and read `payload.run_id`. The subscription
topic and default port are unchanged. There is no dual publication of version 1.
Control and telemetry remain at version 1.

Server integrations should replace `offer_simulation_ended(run_id, state, error)`
with `publish_event(EVENT_SIMULATION_ENDED, payload)`, including `run_id` and `state`
and adding `error` only when it is a string.
