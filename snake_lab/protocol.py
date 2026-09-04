"""SnakeLab ZeroMQ protocol definitions and validation."""

from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
METHOD_HEALTH = "health"
METHOD_SIMULATION_ACTIVE = "simulation.active"
METHOD_SIMULATION_CANCEL = "simulation.cancel"
METHOD_SIMULATION_PAUSE = "simulation.pause"
METHOD_SIMULATION_RESUME = "simulation.resume"
METHOD_SIMULATION_SET_MOVE_DELAY = "simulation.set_move_delay"
METHOD_SIMULATION_STATUS = "simulation.status"
METHOD_SIMULATION_SUBMIT = "simulation.submit"


class ProtocolError(ValueError):
    """A request violates the SnakeLab wire protocol."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Request:
    request_id: str
    method: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "Request":
        if not isinstance(data, dict):
            raise ProtocolError("invalid_request", "Request must be an object")

        expected = {"protocol_version", "request_id", "method", "payload"}
        if set(data) != expected:
            raise ProtocolError(
                "invalid_request", "Request fields do not match the protocol"
            )
        if data["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError(
                "unsupported_protocol", "Unsupported protocol version"
            )
        if not isinstance(data["request_id"], str) or not data["request_id"]:
            raise ProtocolError(
                "invalid_request", "request_id must be a non-empty string"
            )
        if not isinstance(data["method"], str) or not data["method"]:
            raise ProtocolError(
                "invalid_request", "method must be a non-empty string"
            )
        if not isinstance(data["payload"], dict):
            raise ProtocolError("invalid_request", "payload must be an object")

        return cls(data["request_id"], data["method"], data["payload"])


def success_response(
    request_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": "ok",
        "payload": payload,
    }


def error_response(
    request_id: str | None, code: str, message: str
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": "error",
        "error": {"code": code, "message": message},
    }
