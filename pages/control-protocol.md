---
title: Control Protocol
author_profile: true
layout: single
---

[Developer overview](/pages/developer.html) · [Event protocol](/pages/event-protocol.html)

External services submit simulations through a ZeroMQ `REQ` socket connected to
`tcp://wintermute:41970`. Messages are JSON objects using protocol version 1.

Install the Python client dependency:

```sh
pip install pyzmq
```

## Submit a Configuration

The submission payload contains the configuration object itself, not a filename:

```json
{
  "protocol_version": 1,
  "request_id": "4d76309f-7734-49cc-a1b2-ddecd9fc9664",
  "method": "simulation.submit",
  "payload": {
    "config": {
      "epochs": 100,
      "seed": 1970
    }
  }
}
```

Partial configurations are accepted. SnakeLab applies the defaults and validates
the result against the [JSON Schema](/snake_lab/schemas/simulation-config-v1.schema.json).

## Python Client Stub

```python
import asyncio
import json
import sys
import uuid
from pathlib import Path

import zmq
import zmq.asyncio


PROTOCOL_VERSION = 1
ENDPOINT = "tcp://wintermute:41970"
TIMEOUT_SECONDS = 3


class SnakeLabClient:
    def __init__(self, endpoint: str = ENDPOINT) -> None:
        self.endpoint = endpoint
        self.context = zmq.asyncio.Context()

    async def request(self, method: str, payload: dict) -> dict:
        socket = self.context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(self.endpoint)
        request_id = str(uuid.uuid4())
        message = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "payload": payload,
        }

        try:
            await asyncio.wait_for(
                socket.send_json(message), TIMEOUT_SECONDS
            )
            response = await asyncio.wait_for(
                socket.recv_json(), TIMEOUT_SECONDS
            )
        finally:
            socket.close()

        if not isinstance(response, dict):
            raise RuntimeError("invalid SnakeLab response")
        if response.get("protocol_version") != PROTOCOL_VERSION:
            raise RuntimeError("unsupported SnakeLab protocol")
        if response.get("request_id") != request_id:
            raise RuntimeError("SnakeLab request_id mismatch")
        if response.get("status") != "ok":
            error = response.get("error", {})
            code = error.get("code", "request_failed")
            message = error.get("message", "SnakeLab request failed")
            raise RuntimeError(f"{code}: {message}")
        return response["payload"]

    async def submit(self, config: dict) -> dict:
        return await self.request(
            "simulation.submit", {"config": config}
        )

    def close(self) -> None:
        self.context.term()


async def main(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("simulation config must be a JSON object")

    client = SnakeLabClient()
    try:
        result = await client.submit(config)
        print(json.dumps(result, indent=2))
    finally:
        client.close()


asyncio.run(main(sys.argv[1]))
```

Run it with:

```sh
python submit_simulation.py config.json
```

## Responses

Every response echoes `protocol_version` and `request_id`. The example client
validates that envelope and returns only `payload`.

A new submission payload contains its run identifier and queue position:

```json
{
  "run_id": "f6e72cb3-9bcf-4669-b368-a17c656bad79",
  "state": "queued",
  "queue_position": 1
}
```

Every valid submission returns `state: "queued"` and a new `run_id`, even when
the same resolved configuration has already been submitted on this project
version. Earlier runs and their results are preserved. Callers are responsible
for duplicate detection or result reuse if needed. Repeating a request,
including retrying after a timeout, submits another run.

Protocol and configuration failures use this raw response shape:

```json
{
  "protocol_version": 1,
  "request_id": "4d76309f-7734-49cc-a1b2-ddecd9fc9664",
  "status": "error",
  "error": {
    "code": "invalid_config",
    "message": "$.epochs: 10 is less than the minimum of 50"
  }
}
```

The example client converts this into a `RuntimeError`.

## Supported Methods

The server binds a `REP` socket on port 41970 by default. `--port` changes
this port; `--address` selects the bind address for all three interfaces.
Requests contain exactly `protocol_version` (1), a non-empty string
`request_id`, a non-empty string `method`, and an object `payload`.
Payload fields must match the selected method exactly.

| Method | Payload | Successful response payload |
| --- | --- | --- |
| `health` | `{}` | `{"service": "snake-lab"}` |
| `simulation.submit` | `{"config": {...}}` | `run_id`, `state: "queued"`, `queue_position` |
| `simulation.active` | `{}` | `{"run": <run status or null>}`; active run, otherwise first queued run |
| `simulation.status` | `{"run_id": "<run ID>"}` | Run status |
| `simulation.pause` | `{"run_id": "<run ID>"}` | Run status; accepts running or already paused runs |
| `simulation.resume` | `{"run_id": "<run ID>"}` | Run status; accepts paused or already running runs |
| `simulation.cancel` | `{"run_id": "<run ID>"}` | Run status; accepts queued, running, paused, cancelling, or cancelled runs |
| `simulation.set_move_delay` | `{"run_id": "<run ID>", "move_delay_ms": 20}` | Run status; accepts queued, running, or paused runs |

Move delay must be an integer from 0 through 100 in steps of 20 milliseconds.
Cancellation of queued work is immediate. Active work first enters `cancelling`
and later reaches `cancelled`. Pause, resume, cancel, and move delay are runtime
controls, separate from the experiment configuration.

Run status contains `run_id`, `state`, `epochs`, `completed_epochs`, `total_steps`,
`high_score`, `total_reward`, `epsilon_injections`, `last_loss`, `move_delay_ms`,
and `last_episode` (an episode object or null). `error` is included when present.
States are `queued`, `running`, `paused`, `cancelling`, `completed`, `failed`,
and `cancelled`. Status lookup covers runs known to the current server process.

`last_episode`, when present, contains integer `episode`, `seed`, `score`,
`steps`, and `epsilon_injections`; numeric `reward` and `epsilon`; `loss`
(number or null); and string `outcome` (`empty`, `food`, `wall`, `snake`,
`max_moves`, or `board_filled`). `last_loss` is also a number or null.

A successful raw response wraps its payload:

```json
{
  "protocol_version": 1,
  "request_id": "request-123",
  "status": "ok",
  "payload": {"service": "snake-lab"}
}
```

| Error code | Meaning |
| --- | --- |
| `invalid_request` | Invalid envelope, payload fields, or argument values |
| `unsupported_protocol` | Unsupported control protocol version |
| `unknown_method` | Method is not supported |
| `invalid_config` | Configuration failed validation |
| `run_not_found` | Run is unknown to this server process |
| `invalid_run_state` | Operation is unavailable in the run's current state |

For invalid requests, `request_id` may be null if it was unavailable.

Use the same `request()` method from the example for each operation.

