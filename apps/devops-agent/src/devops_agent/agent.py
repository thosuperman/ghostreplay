"""DevOps incident agent harness."""

from __future__ import annotations

import json
from typing import Any

from ghostreplay import AgentResult, AgentRuntime, ToolError
from ghostreplay.mocking import Message, ModelRequest, ToolCallRequest

from .model import MODEL_NAME, SYSTEM_PROMPT
from .safety import DESTRUCTIVE, SafetyGate

MAX_STEPS = 10
MODEL_VISIBLE_TOOLS = {
    "cloudwatch.get_log_events",
    "ec2.describe_instances",
    "deploy.get_status",
    "lambda.invoke",
    "ec2.terminate_instances",
    "deploy.rollback",
    "change.propose",
}


class DevOpsAgent:
    def __init__(self, variant: str) -> None:
        if variant not in ("vulnerable", "fixed"):
            raise ValueError(variant)
        self.variant = variant
        self.name = f"devops-agent/{variant}"
        self.gate = SafetyGate() if variant == "fixed" else None

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        tools = [s.schema() for s in rt.tools.specs() if s.name in MODEL_VISIBLE_TOOLS]
        messages = [Message(role="user", content=task["message"])]
        actions: list[dict[str, Any]] = []
        final = ""
        for _ in range(MAX_STEPS):
            result = rt.complete(
                ModelRequest(model=MODEL_NAME, system=SYSTEM_PROMPT, messages=messages, tools=tools)
            )
            resp = result.response
            messages.append(
                Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
            )
            if not resp.tool_calls:
                final = resp.content
                break
            for call in resp.tool_calls:
                data = self._execute(rt, call, result.event_id)
                if call.name in DESTRUCTIVE or call.name == "change.propose":
                    actions.append({"tool": call.name, "result": data})
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
            final = "Step limit reached; escalating to the on-call human."

        executed = [
            a
            for a in actions
            if a["tool"] in DESTRUCTIVE
            and isinstance(a["result"], (dict, list))
            and not _failed(a["result"])
        ]
        proposed = [
            a for a in actions if a["tool"] == "change.propose" and not _failed(a["result"])
        ]
        status = "success" if (executed or proposed) else "escalated"
        return AgentResult(
            status=status,
            message=final,
            data={"destructive_actions": executed, "proposals": proposed},
        )

    def _execute(self, rt: AgentRuntime, call: ToolCallRequest, parent: str) -> Any:
        if call.name in DESTRUCTIVE and self.gate is not None:
            return self.gate.review(rt, call, parent)
        try:
            return rt.call_tool(call.name, call.arguments, parent_event_id=parent)
        except ToolError as exc:
            return {"error": exc.error_type, "message": exc.message}


def _failed(result: Any) -> bool:
    return isinstance(result, dict) and ("error" in result or result.get("blocked") is True)
