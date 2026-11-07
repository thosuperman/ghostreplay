"""Live model adapter for Claude via the official ``anthropic`` SDK.

The adapter translates GhostReplay's provider-neutral ``ModelRequest`` into a Messages API
request and the response back into a ``ModelResponse``. Everything goes through
``AgentRuntime.complete``, so prompts and responses are recorded and later replayed offline
without calling the API again.

Install with ``uv sync --extra live`` (or ``pip install 'ghostreplay[live]'``).
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..core.errors import GhostReplayError
from ..mocking.model import Message, ModelRequest, ModelResponse, ToolCallRequest

# Tool names in the Messages API must match ^[a-zA-Z0-9_-]{1,64}$; GhostReplay tools use
# dotted names ("payments.create_refund"), so dots are encoded reversibly.
_DOT = "__"
_VALID_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_STOP = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens"}
# Recommended fallback routing for refusals; see the Claude API docs on refusals.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LiveModelError(GhostReplayError):
    """The live model could not produce a usable response (budget, refusal, API error)."""


def encode_tool_name(name: str) -> str:
    encoded = name.replace(".", _DOT)
    if not _VALID_NAME.match(encoded):
        raise LiveModelError(f"tool name {name!r} cannot be expressed for the Messages API")
    return encoded


def decode_tool_name(name: str) -> str:
    return name.replace(_DOT, ".")


def _block_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    dump = getattr(block, "model_dump", None)
    if dump is not None:
        return dump(mode="json", exclude_none=True)
    return dict(vars(block))


def _echo_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Blocks to send back for an assistant turn.

    Blocks are echoed unchanged (thinking blocks included), except that after a mid-output
    fallback the model-internal blocks that precede the final ``fallback`` marker are
    omitted, as the API requires; the marker itself is dropped.
    """
    last_fallback = max(
        (i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1
    )
    internal = {"thinking", "redacted_thinking", "tool_use"}
    out = []
    for i, block in enumerate(blocks):
        if block.get("type") == "fallback":
            continue
        if i < last_fallback and block.get("type") in internal:
            continue
        out.append(block)
    return out


def to_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert provider-neutral messages to Messages API turns.

    Consecutive tool results are grouped into a single user turn, one ``tool_result`` block
    per call, as the API expects.
    """
    out: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush() -> None:
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for m in messages:
        if m.role == "tool":
            if not m.tool_call_id:
                raise LiveModelError(f"tool message for {m.name!r} has no tool_call_id")
            data = m.data
            text = m.content or json.dumps(data, sort_keys=True, default=str)
            pending_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": text,
                    "is_error": isinstance(data, dict) and "error" in data,
                }
            )
            continue
        flush()
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            if m.provider_content is not None:
                out.append({"role": "assistant", "content": _echo_blocks(m.provider_content)})
                continue
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [
                {
                    "type": "tool_use",
                    "id": c.id,
                    "name": encode_tool_name(c.name),
                    "input": c.arguments,
                }
                for c in m.tool_calls
            ]
            out.append({"role": "assistant", "content": blocks})
        # role == "system" is carried by ModelRequest.system
    flush()
    return out


def to_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": encode_tool_name(t["name"]),
            "description": t.get("description", ""),
            "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def from_response(message: Any) -> ModelResponse:
    blocks = [_block_dict(b) for b in getattr(message, "content", [])]
    stop = getattr(message, "stop_reason", None) or "other"
    if stop == "refusal":
        details = _block_dict(getattr(message, "stop_details", None) or {})
        raise LiveModelError(
            "the model declined this request (stop_reason=refusal, "
            f"category={details.get('category')!r}); no response was recorded as success"
        )
    text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    calls = [
        ToolCallRequest(
            id=b["id"], name=decode_tool_name(b["name"]), arguments=dict(b.get("input") or {})
        )
        for b in blocks
        if b.get("type") == "tool_use"
    ]
    usage_obj = getattr(message, "usage", None)
    usage = {
        k: int(v)
        for k, v in (_block_dict(usage_obj) if usage_obj is not None else {}).items()
        if k in ("input_tokens", "output_tokens", "cache_read_input_tokens") and isinstance(v, int)
    }
    return ModelResponse(
        content=text,
        tool_calls=calls,
        stop_reason=_STOP.get(stop, "other"),  # type: ignore[arg-type]
        usage=usage,
        provider_content=blocks,
        served_by=getattr(message, "model", None),
    )


class AnthropicModel:
    """``ModelAdapter`` backed by the Claude Messages API.

    ``client`` may be injected (tests use a fake); otherwise ``anthropic.Anthropic()`` is
    created lazily, resolving credentials from the environment.
    """

    provider = "anthropic"
    is_live = True

    def __init__(
        self,
        model: str,
        *,
        effort: str = "medium",
        max_calls: int = 12,
        max_tokens: int = 16000,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = 0
        self._client = client
        self.label = f"Live LLM: Anthropic {model} (effort {effort})"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise LiveModelError(
                    "live mode needs the 'anthropic' package: uv sync --extra live"
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def build_params(self, request: ModelRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": to_messages(request.messages),
            "output_config": {"effort": self.effort},
            "betas": [_FALLBACK_BETA],
            "fallbacks": "default",
        }
        if request.system:
            params["system"] = request.system
        if request.tools:
            params["tools"] = to_tools(request.tools)
        return params

    def complete(self, request: ModelRequest) -> ModelResponse:
        if self.calls >= self.max_calls:
            raise LiveModelError(
                f"live model call budget exhausted ({self.max_calls} calls per execution)"
            )
        self.calls += 1
        message = self._get_client().beta.messages.create(**self.build_params(request))
        return from_response(message)
