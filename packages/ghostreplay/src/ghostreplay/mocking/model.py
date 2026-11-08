"""Model adapter interface and the deterministic scripted model."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    data: Any = None  # structured tool result (what a function-calling API would carry)
    # Provider-native assistant content (e.g. thinking + tool_use blocks), echoed back
    # unchanged by the live adapter that produced it. Ignored by scripted models.
    provider_content: list[dict[str, Any]] | None = None

    @classmethod
    def assistant(cls, response: ModelResponse) -> Message:
        """The assistant turn for ``response``, keeping provider-native blocks intact."""
        return cls(
            role="assistant",
            content=response.content,
            tool_calls=list(response.tool_calls),
            provider_content=response.provider_content,
        )


class ModelRequest(BaseModel):
    model: str
    system: str = ""
    messages: list[Message]
    tools: list[dict[str, Any]] = Field(default_factory=list)


class ModelResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    stop_reason: Literal["tool_use", "end_turn", "max_tokens", "refusal", "other"] = "end_turn"
    usage: dict[str, int] = Field(default_factory=dict)
    provider_content: list[dict[str, Any]] | None = None
    served_by: str | None = None  # the model that actually answered (live adapters only)


@runtime_checkable
class ModelAdapter(Protocol):
    """Anything that turns a ``ModelRequest`` into a ``ModelResponse``.

    ``provider`` and ``is_live`` are recorded in execution provenance so a scripted response
    is never mistaken for a live LLM response.
    """

    provider: str
    model: str
    is_live: bool
    label: str

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class ScriptedModel:
    """Deterministic policy standing in for an LLM in demos and tests.

    It reads the conversation (including structured tool results) and decides the next tool
    call or final answer with plain Python. It is labelled ``scripted`` everywhere.
    """

    provider = "scripted"
    is_live = False

    def __init__(
        self,
        model: str,
        policy: Callable[[ModelRequest], ModelResponse],
        *,
        label: str | None = None,
    ) -> None:
        self.model = model
        self._policy = policy
        self.label = label or (
            f"Scripted demonstration model '{model}' (deterministic policy, not a live LLM)"
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self._policy(request)
        if not response.usage:
            prompt_chars = sum(len(m.content) for m in request.messages)
            response.usage = {"input_chars": prompt_chars, "output_chars": len(response.content)}
        return response


class RecordedDecisionsModel:
    """Stands in for a live model when re-executing a genuine live capture without credentials.

    In a branch re-execution, GhostReplay serves every model call from the capture for as long
    as the run follows it; this adapter is only reached if the run leaves the captured path
    (the agent asks the model something the capture does not contain). It then fails loudly
    instead of inventing a decision.
    """

    is_live = False

    def __init__(self, provider: str, model: str, capture_id: str) -> None:
        self.provider = provider
        self.model = model
        self.capture_id = capture_id
        self.label = (
            f"Recorded decisions of {model} ({provider}) from genuine capture {capture_id}: "
            "model calls are served from the capture, no live model call is made"
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        from ..core.errors import GhostReplayError

        raise GhostReplayError(
            f"this re-execution left the path recorded in capture {self.capture_id}, so it needs "
            "a new model decision; enable live AI mode (GHOSTREPLAY_LIVE=1 and a provider key) "
            "to continue it with a live model"
        )
