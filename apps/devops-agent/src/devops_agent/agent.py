"""DevOps incident agent harness."""

from __future__ import annotations

import json
from typing import Any

from ghostreplay import AgentResult, AgentRuntime, ToolError
from ghostreplay.mocking import Message, ModelRequest, ToolCallRequest

from .model import RUNBOOKS
from .safety import DESTRUCTIVE, SafetyGate

MAX_STEPS = 10
#: Tools each version of the workflow exposes to the model.
MODEL_VISIBLE_TOOLS = {
    "vulnerable": {
        "cloudwatch.get_log_events",
        "ec2.describe_instances",
        "ec2.terminate_instances",
    },
    "fixed": {
        "cloudwatch.get_log_events",
        "ec2.describe_instances",
        "ec2.get_instance_status",
        "deploy.get_status",
        "lambda.invoke",
        "ec2.terminate_instances",
        "deploy.rollback",
        "change.propose",
    },
}


class DevOpsAgent:
    def __init__(self, variant: str) -> None:
        if variant not in ("vulnerable", "fixed"):
            raise ValueError(variant)
        self.variant = variant
        self.name = f"devops-agent/{variant}"
        self.gate = SafetyGate() if variant == "fixed" else None

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        visible = MODEL_VISIBLE_TOOLS[self.variant]
        tools = [s.schema() for s in rt.tools.specs() if s.name in visible]
        system = RUNBOOKS[self.variant]
        messages = [Message(role="user", content=task["message"])]
        actions: list[dict[str, Any]] = []
        final = ""
        for _ in range(MAX_STEPS):
            result = rt.complete(
                ModelRequest(model=rt.model_name, system=system, messages=messages, tools=tools)
            )
            resp = result.response
            messages.append(Message.assistant(resp))
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
