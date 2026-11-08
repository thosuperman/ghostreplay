"""Tools for the DevOps agent. Every call is a real HTTP request to the lab controller.

The tool names mirror familiar cloud APIs, but they only ever reach the isolated lab on
127.0.0.1 (see ``lab.py``). ``build_tools(None)`` returns the specifications only, for strict
offline replay where no handler may run.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field

from ghostreplay.mocking import ToolRegistry, ToolSpec

from .environment import SERVICE
from .lab import InfraLab


class GetLogs(BaseModel):
    log_group: str = Field(pattern=r"^/[\w/\-]+$")
    contains: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class Service(BaseModel):
    service: str


class InstanceId(BaseModel):
    instance_id: str = Field(pattern=r"^i-[0-9a-f]{6,17}$")


class InvokeFn(BaseModel):
    function: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SimulatePermission(BaseModel):
    action: str
    resource: str = "*"


class Terminate(BaseModel):
    instance_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str


class Rollback(BaseModel):
    service: str
    reason: str


class ProposeChange(BaseModel):
    title: str
    action: str
    target: str
    rationale: str
    risk: str = "medium"
    evidence: list[str] = Field(default_factory=list)


def build_tools(lab: InfraLab | None) -> ToolRegistry:
    reg = ToolRegistry()

    def L() -> InfraLab:
        if lab is None:  # pragma: no cover - offline registries never call handlers
            raise RuntimeError("no lab: this registry is for offline replay only")
        return lab

    def timed(fn):  # record the real wall-clock latency of the HTTP call as the duration
        def run(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                if lab is not None and lab.run_clock is not None:
                    lab.run_clock.advance(round((time.perf_counter() - t0) * 1000, 1))

        return run

    def capacity(args: dict[str, Any]) -> dict[str, Any]:
        targets = args.get("instance_ids") or []
        insts = L().cloud.instances
        return {
            "targets": {i: insts[i]["state"] for i in targets if i in insts},
            "running_instances": sum(
                1 for i in insts.values() if i["service"] == SERVICE and i["state"] == "running"
            ),
        }

    reg.register(
        ToolSpec(
            "cloudwatch.get_log_events",
            timed(
                lambda log_group, limit=20, contains=None: L().get(
                    "/v1/logs?"
                    + urlencode(
                        {
                            "log_group": log_group,
                            "limit": limit,
                            **({"contains": contains} if contains else {}),
                        }
                    )
                )
            ),
            "Read recent log events from the lab controller.",
            "http",
            args_model=GetLogs,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.describe_instances",
            timed(lambda service: L().get("/v1/instances?" + urlencode({"service": service}))),
            "List instances of a service with their aggregated status checks.",
            "http",
            args_model=Service,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.get_instance_status",
            timed(lambda instance_id: L().get(f"/v1/instances/{quote(instance_id)}/status")),
            "Probe one instance directly (fresh status).",
            "http",
            args_model=InstanceId,
        )
    )
    reg.register(
        ToolSpec(
            "deploy.get_status",
            timed(lambda service: L().get(f"/v1/deployments/{quote(service)}")),
            "Current and previous deployment for a service.",
            "http",
            args_model=Service,
        )
    )
    reg.register(
        ToolSpec(
            "lambda.invoke",
            timed(
                lambda function, payload=None: L().post(
                    f"/v1/functions/{quote(function)}/invoke", {"payload": payload or {}}
                )
            ),
            "Invoke a diagnostic function (Lambda-like).",
            "http",
            args_model=InvokeFn,
        )
    )
    reg.register(
        ToolSpec(
            "iam.simulate_permission",
            timed(
                lambda action, resource="*": L().post(
                    "/v1/iam/simulate", {"action": action, "resource": resource}
                )
            ),
            "Check whether the agent role may perform an action.",
            "http",
            args_model=SimulatePermission,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.terminate_instances",
            timed(
                lambda instance_ids, reason: L().post(
                    "/v1/instances/terminate", {"instance_ids": instance_ids, "reason": reason}
                )
            ),
            "Terminate instances (destructive).",
            "http",
            destructive=True,
            args_model=Terminate,
            observe=capacity,
        )
    )
    reg.register(
        ToolSpec(
            "deploy.rollback",
            timed(
                lambda service, reason: L().post(
                    f"/v1/deployments/{quote(service)}/rollback", {"reason": reason}
                )
            ),
            "Roll a service back to its previous version (destructive).",
            "http",
            destructive=True,
            args_model=Rollback,
        )
    )
    reg.register(
        ToolSpec(
            "change.propose",
            timed(lambda **p: L().post("/v1/changes", p)),
            "File a change proposal for human approval (no infrastructure change).",
            "agent",
            args_model=ProposeChange,
        )
    )
    return reg
