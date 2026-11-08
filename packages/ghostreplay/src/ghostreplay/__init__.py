"""GhostReplay: deterministic replay and failure testing for AI agents.

Break AI agents safely. Replay failures. Prove the fix.
"""

__version__ = "0.1.0"

from .core.clock import DeterministicSources, SystemClock, VirtualClock
from .core.errors import (
    AuthError,
    GhostReplayError,
    HttpError,
    MissingRecordingError,
    OfflineViolation,
    PartialFailure,
    PermissionDenied,
    RateLimited,
    ReplayDivergenceError,
    ToolError,
    ToolTimeout,
    TraceFormatError,
)
from .models import (
    AgentResult,
    Event,
    EventKind,
    EventSource,
    Execution,
    ExecutionMode,
    FaultPreset,
    FaultSpec,
    FaultTarget,
)
from .regression.invariants import Check, Invariant, TraceView
from .runtime import AgentRuntime, ModelResult
from .sdk import GhostReplay, Run, fault

__all__ = [
    "AgentResult",
    "AgentRuntime",
    "AuthError",
    "Check",
    "DeterministicSources",
    "Event",
    "EventKind",
    "EventSource",
    "Execution",
    "ExecutionMode",
    "FaultPreset",
    "FaultSpec",
    "FaultTarget",
    "GhostReplay",
    "GhostReplayError",
    "HttpError",
    "Invariant",
    "MissingRecordingError",
    "ModelResult",
    "OfflineViolation",
    "PartialFailure",
    "PermissionDenied",
    "RateLimited",
    "ReplayDivergenceError",
    "Run",
    "SystemClock",
    "ToolError",
    "ToolTimeout",
    "TraceFormatError",
    "TraceView",
    "VirtualClock",
    "__version__",
    "fault",
]
