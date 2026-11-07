"""The Recorder appends redacted, sequenced events to an Execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.canonical import to_jsonable
from ..core.clock import Clock
from ..models import (
    AppliedFault,
    ErrorInfo,
    Event,
    EventKind,
    EventSource,
    Execution,
    ReplayAnnotation,
)
from .redaction import Redactor

EventListener = Callable[[Event], None]


class Recorder:
    """Builds the event log of one execution.

    Guarantees: events get strictly increasing ``seq``; every payload passes through the
    redactor before it is stored; listeners observe events in order as they are appended
    (the Replay Studio streams from a listener).
    """

    def __init__(
        self,
        execution: Execution,
        clock: Clock,
        *,
        redactor: Redactor | None = None,
        listeners: list[EventListener] | None = None,
    ) -> None:
        self.execution = execution
        self.clock = clock
        self.redactor = redactor or Redactor()
        self._listeners: list[EventListener] = list(listeners or [])

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    @property
    def next_seq(self) -> int:
        return len(self.execution.events)

    def emit(
        self,
        kind: EventKind,
        name: str,
        *,
        source: EventSource,
        timestamp: str | None = None,
        duration_ms: float = 0.0,
        parent_event_id: str | None = None,
        agent: str | None = None,
        model: str | None = None,
        request: Any = None,
        response: Any = None,
        error: ErrorInfo | dict[str, Any] | None = None,
        state_before: Any = None,
        state_after: Any = None,
        match_key: str | None = None,
        destructive: bool = False,
        fault: AppliedFault | None = None,
        replay: ReplayAnnotation | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        r = self.redactor.redact
        seq = self.next_seq
        if isinstance(error, dict):
            error = ErrorInfo(**error)
        if error is not None:
            error = ErrorInfo(**r(error.model_dump()))
        if fault is not None:
            fault = fault.model_copy(
                update={
                    "original_response": r(to_jsonable(fault.original_response)),
                    "original_error": (
                        ErrorInfo(**r(fault.original_error.model_dump()))
                        if fault.original_error
                        else None
                    ),
                }
            )
        event = Event(
            execution_id=self.execution.id,
            event_id=f"{self.execution.id}.{seq:04d}",
            parent_event_id=parent_event_id,
            seq=seq,
            kind=kind,
            name=name,
            timestamp=timestamp or self.clock.now().isoformat(),
            duration_ms=round(float(duration_ms), 3),
            agent=agent or self.execution.agent,
            source=source,
            model=model,
            request=r(to_jsonable(request)),
            response=r(to_jsonable(response)),
            error=error,
            state_before=r(to_jsonable(state_before)),
            state_after=r(to_jsonable(state_after)),
            match_key=match_key,
            destructive=destructive,
            fault=fault,
            replay=replay,
            metadata=r(to_jsonable(metadata or {})),
        )
        self.execution.events.append(event)
        for listener in self._listeners:
            listener(event)
        return event
