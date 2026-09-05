"""Event wire contract, independent of the ZeroMQ transport."""

from typing import Any

from snake_lab.protocol import ProtocolError


EVENT_PROTOCOL_VERSION = 2
EVENT_SIMULATION_ENDED = "simulation_ended"
TOPIC_SIMULATION_ENDED = "snake_lab.simulation.ended"
EVENT_TOPICS = {EVENT_SIMULATION_ENDED: TOPIC_SIMULATION_ENDED}


def event_message(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an event and return an envelope owning a copy of its payload."""
    if not isinstance(event_type, str) or event_type not in EVENT_TOPICS:
        raise ProtocolError("unknown_event", "Unsupported event type")
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_event", "payload must be an object")
    if event_type == EVENT_SIMULATION_ENDED:
        required = {"run_id", "state"}
        if not required <= set(payload) or set(payload) - required - {"error"}:
            raise ProtocolError(
                "invalid_event", "Event payload fields do not match the protocol"
            )
        if not isinstance(payload["run_id"], str) or not payload["run_id"]:
            raise ProtocolError("invalid_event", "run_id must be a non-empty string")
        if not isinstance(payload["state"], str) or payload["state"] not in {
            "completed", "failed", "cancelled"
        }:
            raise ProtocolError(
                "invalid_event", "simulation ended requires a terminal state"
            )
        if "error" in payload and not isinstance(payload["error"], str):
            raise ProtocolError(
                "invalid_event", "error must be a string when present"
            )
    return {
        "protocol_version": EVENT_PROTOCOL_VERSION,
        "event_type": event_type,
        "payload": dict(payload),
    }


def parse_event(data: Any) -> dict[str, Any]:
    """Validate a decoded incoming event, rejecting unsupported versions/types."""
    if not isinstance(data, dict) or set(data) != {
        "protocol_version", "event_type", "payload"
    }:
        raise ProtocolError("invalid_event", "Event fields do not match the protocol")
    if (
        type(data["protocol_version"]) is not int
        or data["protocol_version"] != EVENT_PROTOCOL_VERSION
    ):
        raise ProtocolError(
            "unsupported_protocol", "Unsupported event protocol version"
        )
    return event_message(data["event_type"], data["payload"])
