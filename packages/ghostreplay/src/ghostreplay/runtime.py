"""AgentRuntime: the single door between an agent and the outside world.

Agents written against this interface can be recorded, replayed offline, mutated and
branch-executed without any change to their code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .core.errors import ToolError, ToolValidationError, UnknownToolError
from .mocking.model import ModelAdapter, ModelRequest, ModelResponse
from .mocking.tools import ToolRegistry
from .models import Event, EventKind, EventSource
from .replay.session import Operation, Session


class NondeterminismSource(Protocol):
    def new_id(self, prefix: str = "id") -> str: ...

    def random(self) -> float: ...


@dataclass
class ModelResult:
    response: ModelResponse
    event_id: str


class AgentRuntime:
    def __init__(
        self,
        session: Session,
        *,
        tools: ToolRegistry,
        model: ModelAdapter | None,
        sources: NondeterminismSource,
        agent_name: str,
        model_name: str | None = None,
    ) -> None:
        self.session = session
        self.tools = tools
        self.model = model
        self.sources = sources
        self.agent_name = agent_name
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        """Model id agents should put in ``ModelRequest.model``.

        During offline replay there is no adapter, so the name comes from the recording's
        provenance; this keeps replay of live-model recordings matching call for call.
        """
        if self._model_name:
            return self._model_name
        if self.model is not None:
            return self.model.model
        raise RuntimeError("no model adapter and no recorded model name")

    @property
    def clock(self):
        return self.session.clock

    # -- model --------------------------------------------------------------------------
    def complete(self, request: ModelRequest, *, parent_event_id: str | None = None) -> ModelResult:
        """Ask the model for the next step. Served from the recording when replaying."""
        model = self.model

        def invoke() -> dict[str, Any]:
            if model is None:
                raise RuntimeError("no model adapter available (offline replay)")
            return model.complete(request).model_dump(mode="json", exclude_none=True)

        payload, event = self.session.interact(
            Operation(
                kind=EventKind.MODEL_CALL,
                name=request.model,
                model=request.model,
                request=request.model_dump(mode="json", exclude_none=True),
                parent_event_id=parent_event_id,
            ),
            invoke,
        )
        return ModelResult(ModelResponse.model_validate(payload), event.event_id)

    # -- tools ---------------------------------------------------------------------------
    def call_tool(
        self, name: str, args: dict[str, Any] | None = None, *, parent_event_id: str | None = None
    ) -> Any:
        """Call an allowlisted tool. Raises ``ToolError`` subclasses on failure."""
        args = dict(args or {})
        try:
            spec = self.tools.get(name)
        except UnknownToolError as exc:
            spec = None
            unknown = str(exc)

        if spec is None:

            def invoke_unknown() -> Any:
                raise ToolError(unknown, data={"tool": name})

            response, _ = self.session.interact(
                Operation(
                    kind=EventKind.TOOL_CALL,
                    name=name,
                    request=args,
                    parent_event_id=parent_event_id,
                ),
                invoke_unknown,
            )
            return response

        match_request = {k: args.get(k) for k in spec.match_fields} if spec.match_fields else args

        def invoke() -> Any:
            validated = spec.validate(args)
            return spec.handler(**validated)

        observe = (lambda: spec.observe(args)) if spec.observe else None  # type: ignore[misc]
        response, _ = self.session.interact(
            Operation(
                kind=EventKind.TOOL_CALL,
                name=name,
                request=args,
                destructive=spec.destructive,
                timeout_ms=spec.timeout_ms,
                observe=observe,
                match_request=match_request,
                parent_event_id=parent_event_id,
                metadata={"category": spec.category},
            ),
            invoke,
        )
        return response

    # -- nondeterminism ----------------------------------------------------------------
    def now(self) -> str:
        value, _ = self.session.interact(
            Operation(kind=EventKind.NONDETERMINISM, name="clock.now", request=None),
            lambda: self.session.clock.now().isoformat(),
        )
        return str(value)

    def new_id(self, prefix: str = "id") -> str:
        value, _ = self.session.interact(
            Operation(kind=EventKind.NONDETERMINISM, name="ids.new", request={"prefix": prefix}),
            lambda: self.sources.new_id(prefix),
        )
        return str(value)

    def random(self) -> float:
        value, _ = self.session.interact(
            Operation(kind=EventKind.NONDETERMINISM, name="random.random", request=None),
            self.sources.random,
        )
        return float(value)

    # -- annotations (not replayed, but recorded and diffed) -------------------------------
    def log(
        self, step: str, detail: dict[str, Any] | None = None, *, parent_event_id: str | None = None
    ) -> Event:
        """Record an agent-declared step (e.g. 'retrying after timeout')."""
        return self.session.recorder.emit(
            EventKind.AGENT_STEP,
            step,
            source=EventSource.FRAMEWORK,
            request=detail or {},
            parent_event_id=parent_event_id,
        )

    def guard(
        self, decision: str, detail: dict[str, Any], *, parent_event_id: str | None = None
    ) -> Event:
        """Record a safety-guard decision (e.g. a blocked destructive action)."""
        return self.session.recorder.emit(
            EventKind.GUARD,
            decision,
            source=EventSource.FRAMEWORK,
            request=detail,
            parent_event_id=parent_event_id,
        )


__all__ = ["AgentRuntime", "ModelResult", "NondeterminismSource", "ToolValidationError"]
