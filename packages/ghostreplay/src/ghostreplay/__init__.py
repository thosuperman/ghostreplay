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
from .runtime import AgentRuntime, ModelResult

__all__ = [
    "AgentResult",
    "AgentRuntime",
    "AuthError",
    "DeterministicSources",
    "Event",
    "EventKind",
    "EventSource",
    "Execution",
    "ExecutionMode",
    "FaultPreset",
    "FaultSpec",
    "FaultTarget",
    "GhostReplayError",
    "HttpError",
    "MissingRecordingError",
    "ModelResult",
    "OfflineViolation",
    "PartialFailure",
    "PermissionDenied",
    "RateLimited",
    "ReplayDivergenceError",
    "SystemClock",
    "ToolError",
    "ToolTimeout",
    "TraceFormatError",
    "VirtualClock",
    "__version__",
]
