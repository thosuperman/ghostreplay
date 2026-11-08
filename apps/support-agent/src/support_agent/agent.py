"""The support agent harness: a tool-calling loop around the model.

Both variants share the loop and the model. They differ only in how a refund is executed —
which is exactly where the real bug lives.
"""

from __future__ import annotations

import json
from typing import Any

from ghostreplay import AgentResult, AgentRuntime, RateLimited, ToolError, ToolTimeout
from ghostreplay.mocking import Message, ModelRequest, ToolCallRequest

from .model import SYSTEM_PROMPT

MAX_STEPS = 8
MAX_REFUND_ATTEMPTS = 3


def _model_facing(schema: dict[str, Any]) -> dict[str, Any]:
    """Tool schema as shown to the model. Idempotency is the application's job, so the model
    is never asked for a key (a live model will otherwise invent one, which hides the bug the
    vulnerable version represents and is not something the fixed version should rely on)."""
    params = schema.get("parameters") or {}
    props = params.get("properties") or {}
    if "idempotency_key" not in props:
        return schema
    props = {k: v for k, v in props.items() if k != "idempotency_key"}
    required = [r for r in params.get("required", []) if r != "idempotency_key"]
    return {**schema, "parameters": {**params, "properties": props, "required": required}}


def _error(exc: ToolError) -> dict[str, Any]:
    return {"error": exc.error_type, "message": exc.message}


class SupportAgent:
    def __init__(self, variant: str) -> None:
        if variant not in ("vulnerable", "fixed"):
            raise ValueError(variant)
        self.variant = variant
        self.name = f"support-agent/{variant}"

    # -- main loop ------------------------------------------------------------------------
    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        tools = [_model_facing(s.schema()) for s in rt.tools.specs() if s.name != "crm.send_reply"]
        messages = [Message(role="user", content=task["message"])]
        refund: dict[str, Any] | None = None
        final = ""
        for _ in range(MAX_STEPS):
            result = rt.complete(
                ModelRequest(
                    model=rt.model_name, system=SYSTEM_PROMPT, messages=messages, tools=tools
                )
            )
            resp = result.response
            messages.append(Message.assistant(resp))
            if not resp.tool_calls:
                final = resp.content
                break
            for call in resp.tool_calls:
                data = self._execute(rt, call, task, result.event_id)
                if call.name == "payments.create_refund" and "error" not in data:
                    refund = data
                messages.append(
                    Message(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        data=data,
                        content=json.dumps(data, sort_keys=True),
                    )
                )
        else:
            final = "I've escalated your request to a specialist."

        rt.call_tool(
            "crm.send_reply",
            {"customer_id": task["customer_id"], "ticket_id": task["ticket_id"], "message": final},
        )
        if refund is not None:
            status = "success"
        elif "isn't eligible" in final:
            status = "refused"
        else:
            status = "escalated"
        return AgentResult(status=status, message=final, data={"refund": refund})

    def _execute(
        self, rt: AgentRuntime, call: ToolCallRequest, task: dict[str, Any], parent: str
    ) -> dict[str, Any]:
        if call.name == "payments.create_refund":
            if self.variant == "vulnerable":
                return self._refund_naive(rt, dict(call.arguments), parent)
            return self._refund_idempotent(rt, dict(call.arguments), task, parent)
        try:
            return rt.call_tool(call.name, call.arguments, parent_event_id=parent)
        except ToolError as exc:
            return _error(exc)

    # -- the bug ----------------------------------------------------------------------------
    def _refund_naive(self, rt: AgentRuntime, args: dict[str, Any], parent: str) -> dict[str, Any]:
        """Retry on timeout with an identical, non-idempotent request.

        A timeout is ambiguous: the gateway may already have committed the refund. Retrying a
        non-idempotent POST in that situation can move the money twice. This version of the
        application's refund client has no idempotency support, so no key is ever sent. The
        retry is the application's retry policy, not a model decision.
        """
        args.pop("idempotency_key", None)
        last: ToolError | None = None
        for attempt in range(1, MAX_REFUND_ATTEMPTS + 1):
            try:
                return rt.call_tool("payments.create_refund", args, parent_event_id=parent)
            except (ToolTimeout, RateLimited) as exc:
                last = exc
                rt.log(
                    "retry",
                    {"attempt": attempt, "reason": exc.error_type, "idempotency_key": None},
                    parent_event_id=parent,
                )
            except ToolError as exc:
                return _error(exc)
        assert last is not None
        return _error(last)

    # -- the fix ----------------------------------------------------------------------------
    def _refund_idempotent(
        self, rt: AgentRuntime, args: dict[str, Any], task: dict[str, Any], parent: str
    ) -> dict[str, Any]:
        """Make the refund idempotent end to end.

        1. The idempotency key is derived from the business intent (ticket + payment + amount),
           so every attempt — even after a crash and restart — maps to the same refund.
        2. After an ambiguous timeout, reconcile with the gateway before retrying.
        3. Retries reuse the same key, so the gateway returns the original refund.
        """
        key = f"refund:{task['ticket_id']}:{args.get('payment_id')}:{args.get('amount_cents')}"
        args = {**args, "idempotency_key": key}
        last: ToolError | None = None
        for attempt in range(1, MAX_REFUND_ATTEMPTS + 1):
            try:
                return rt.call_tool("payments.create_refund", args, parent_event_id=parent)
            except ToolTimeout as exc:
                last = exc
                rt.log(
                    "ambiguous_failure",
                    {
                        "attempt": attempt,
                        "idempotency_key": key,
                        "action": "reconcile before retry",
                    },
                    parent_event_id=parent,
                )
                try:
                    ledger = rt.call_tool(
                        "payments.list_refunds",
                        {"payment_id": args.get("payment_id")},
                        parent_event_id=parent,
                    )
                except ToolError:
                    continue  # still unknown; the retry below is safe because of the key
                committed = next(
                    (r for r in ledger.get("data", []) if r.get("idempotency_key") == key), None
                )
                if committed is not None:
                    rt.log(
                        "recovered",
                        {
                            "recovers": getattr(exc, "event_id", None),
                            "refund_id": committed["id"],
                            "how": "found committed refund by idempotency key",
                        },
                        parent_event_id=parent,
                    )
                    return {**committed, "reconciled": True}
            except RateLimited as exc:
                last = exc
                rt.log(
                    "retry",
                    {"attempt": attempt, "reason": "rate_limited", "idempotency_key": key},
                    parent_event_id=parent,
                )
            except ToolError as exc:
                return _error(exc)
        assert last is not None
        return _error(last)
