"""Common envelope for telemetry messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snake_lab.zmq.Protocol import PROTOCOL_VERSION, ProtocolError


@dataclass(frozen=True, slots=True)
class TelemetryEnvelope:
    """Common JSON envelope carried after the ZeroMQ topic frame."""

    sequence: int
    run_id: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "TelemetryEnvelope":
        if not isinstance(data, dict):
            raise ProtocolError(
                "invalid_telemetry", "telemetry envelope must be an object"
            )
        expected = {"protocol_version", "sequence", "run_id", "payload"}
        if set(data) != expected:
            raise ProtocolError(
                "invalid_telemetry",
                "telemetry envelope fields do not match the protocol",
            )
        if data["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError(
                "unsupported_protocol", "Unsupported telemetry protocol"
            )
        if type(data["sequence"]) is not int or data["sequence"] < 0:
            raise ProtocolError(
                "invalid_telemetry", "sequence must be a non-negative integer"
            )
        if not isinstance(data["run_id"], str) or not data["run_id"]:
            raise ProtocolError(
                "invalid_telemetry", "run_id must be a non-empty string"
            )
        if not isinstance(data["payload"], dict):
            raise ProtocolError(
                "invalid_telemetry", "payload must be an object"
            )
        return cls(data["sequence"], data["run_id"], data["payload"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "sequence": self.sequence,
            "run_id": self.run_id,
            "payload": self.payload,
        }
