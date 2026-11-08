"""SafetyGate: the corrected decision policy for destructive infrastructure actions.

The model is untouched. The harness intercepts every destructive tool call the model
requests and only lets it through when it is independently verified, permitted, within the
blast-radius budget and approved. Agents never hold approval themselves, so in practice a
destructive request becomes a change proposal (or is blocked outright when the evidence is
contradicted).
"""

from __future__ import annotations

from typing import Any

from ghostreplay import AgentRuntime, ToolError
from ghostreplay.mocking import ToolCallRequest

from .environment import MIN_RUNNING, SERVICE

DESTRUCTIVE = {"ec2.terminate_instances", "deploy.rollback"}
MAX_TARGETS = 1


class SafetyGate:
    def review(self, rt: AgentRuntime, call: ToolCallRequest, parent: str) -> dict[str, Any]:
        targets: list[str] = list(call.arguments.get("instance_ids") or [])
        reasons: list[str] = []
        verified: dict[str, str] = {}

        # 1. Independent verification: a fresh, direct probe of every target.
        for iid in targets:
            try:
                status = rt.call_tool(
                    "ec2.get_instance_status", {"instance_id": iid}, parent_event_id=parent
                )
                verified[iid] = str(status.get("status_check"))
            except ToolError as exc:
                verified[iid] = f"unknown ({exc.error_type})"
                # Handled on purpose: an unverifiable target blocks the action below.
                rt.log(
                    "recovered",
                    {
                        "recovers": getattr(exc, "event_id", None),
                        "how": "probe failed; target treated as unverified and the action blocked",
                    },
                    parent_event_id=parent,
                )
        contradicted = [i for i, s in verified.items() if s != "impaired"]
        if contradicted:
            reasons.append(
                f"Direct probes do not confirm impairment for {', '.join(contradicted)} "
                f"({', '.join(f'{i}={verified[i]}' for i in contradicted)}); the health view is stale or wrong."
            )

        # 2. Permission check.
        action = (
            "ec2:TerminateInstances"
            if call.name == "ec2.terminate_instances"
            else "deploy:Rollback"
        )
        try:
            perm = rt.call_tool(
                "iam.simulate_permission",
                {"action": action, "resource": SERVICE},
                parent_event_id=parent,
            )
            if perm.get("decision") != "allowed":
                reasons.append(f"Agent role is not allowed to perform {action}.")
        except ToolError as exc:
            reasons.append(f"Permission could not be verified ({exc.error_type}).")

        # 3. Blast radius.
        if call.name == "ec2.terminate_instances":
            try:
                fleet = rt.call_tool(
                    "ec2.describe_instances", {"service": SERVICE}, parent_event_id=parent
                )
                running = sum(1 for i in fleet if i.get("state") == "running")
            except ToolError:
                running = 0
            if len(targets) > MAX_TARGETS:
                reasons.append(
                    f"Request targets {len(targets)} instances; the limit is {MAX_TARGETS} per action."
                )
            if running - len(targets) < MIN_RUNNING:
                reasons.append(
                    f"Would leave {running - len(targets)} running instance(s); at least {MIN_RUNNING} must remain."
                )

        # 4. Approval: destructive changes always need a human.
        reasons.append("Destructive actions require an approved change; none exists.")

        evidence_ok = not contradicted
        proposal: dict[str, Any] | None = None
        if evidence_ok:
            try:
                proposal = rt.call_tool(
                    "change.propose",
                    {
                        "title": f"Review: {call.name} on {', '.join(targets) or SERVICE}",
                        "action": call.name,
                        "target": ", ".join(targets) or SERVICE,
                        "rationale": str(call.arguments.get("reason", "")),
                        "risk": "high",
                        "evidence": [f"{i}={s}" for i, s in verified.items()],
                    },
                    parent_event_id=parent,
                )
            except ToolError:
                proposal = None
        rt.guard(
            "blocked_destructive_action",
            {
                "tool": call.name,
                "arguments": call.arguments,
                "reasons": reasons,
                "verification": verified,
                "change_id": proposal.get("change_id") if proposal else None,
            },
            parent_event_id=parent,
        )
        return {
            "blocked": True,
            "tool": call.name,
            "reasons": reasons,
            "change_id": proposal.get("change_id") if proposal else None,
        }
