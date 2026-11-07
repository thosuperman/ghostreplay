"""Exception hierarchy for GhostReplay.

Two families:

* Framework errors (``GhostReplayError``) describe problems with recording or replay itself
  (divergence, missing recordings, offline violations). Agents must not swallow them; the
  session records them even if they are caught.
* Tool errors (``ToolError``) are the errors an agent legitimately sees from the world
  (timeouts, HTTP failures, permission problems). They are serialisable so that replay can
  re-raise exactly what was recorded.
"""

from __future__ import annotations

from typing import Any


class GhostReplayError(Exception):
    """Base class for framework-level errors."""


class ReplayDivergenceError(GhostReplayError):
    """The agent issued an interaction that does not match the recording."""

    def __init__(self, message: str, *, divergence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.divergence = divergence or {}


class MissingRecordingError(ReplayDivergenceError):
    """The agent issued an interaction but the recording has nothing left to serve."""


class OfflineViolation(GhostReplayError):
    """Something attempted network or real side-effect access during offline replay."""


class UnknownToolError(GhostReplayError):
    """The agent called a tool that is not in the allowlisted registry."""


class ScenarioNotFound(GhostReplayError):
    """A scenario id could not be resolved from the registry."""


class ExecutionNotFound(GhostReplayError):
    """An execution id is not present in the store."""


class UnsafePathError(GhostReplayError):
    """A file path escaped its permitted base directory."""


class TraceFormatError(GhostReplayError, ValueError):
    """Stored or imported data is not a valid GhostReplay document (bad JSON, wrong schema,
    out-of-order events, ...). Raised instead of loading a partially valid recording."""


# ---------------------------------------------------------------------------------------
# Errors visible to agents
# ---------------------------------------------------------------------------------------


class ToolError(Exception):
    """An error returned by a tool. Serialisable and safe to rebuild from a trace."""

    error_type = "ToolError"
    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        retryable: bool | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = self.default_retryable if retryable is None else retryable
        self.data = data or {}

    def to_info(self) -> dict[str, Any]:
        return {
            "type": self.error_type,
            "message": self.message,
            "retryable": self.retryable,
            "data": self.data,
        }

    @staticmethod
    def from_info(info: dict[str, Any]) -> ToolError:
        """Rebuild a recorded error through an allowlist (never imports arbitrary types)."""
        type_name = str(info.get("type") or "ToolError")
        cls = _ERROR_TYPES.get(type_name, ToolError)
        err = cls(
            str(info.get("message", "")),
            retryable=bool(info.get("retryable", False)),
            data=dict(info.get("data") or {}),
        )
        if cls is ToolError and type_name != "ToolError":
            # Preserve the recorded type name for fidelity without importing anything.
            err.error_type = type_name
        return err


class ToolTimeout(ToolError):
    error_type = "ToolTimeout"
    default_retryable = True


class HttpError(ToolError):
    error_type = "HttpError"

    @property
    def status(self) -> int:
        return int(self.data.get("status", 0))


class RateLimited(HttpError):
    error_type = "RateLimited"
    default_retryable = True


class AuthError(ToolError):
    error_type = "AuthError"


class PermissionDenied(ToolError):
    error_type = "PermissionDenied"


class PartialFailure(ToolError):
    error_type = "PartialFailure"


class ToolValidationError(ToolError):
    error_type = "ToolValidationError"


class AgentCrash(ToolError):
    """Used only to describe an unexpected exception raised by agent code."""

    error_type = "AgentCrash"


_ERROR_TYPES: dict[str, type[ToolError]] = {
    cls.error_type: cls
    for cls in (
        ToolError,
        ToolTimeout,
        HttpError,
        RateLimited,
        AuthError,
        PermissionDenied,
        PartialFailure,
        ToolValidationError,
        AgentCrash,
    )
}


def register_error_type(cls: type[ToolError]) -> type[ToolError]:
    """Allow an application-defined ``ToolError`` subclass to be rebuilt during replay."""
    _ERROR_TYPES[cls.error_type] = cls
    return cls
