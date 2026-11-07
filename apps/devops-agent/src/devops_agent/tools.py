"""Mocked AWS-style tools for the DevOps agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ghostreplay.mocking import MockAwsCloud, ToolRegistry, ToolSpec

from .environment import AGENT_ROLE, SERVICE


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


def build_tools(cloud: MockAwsCloud) -> ToolRegistry:
    reg = ToolRegistry()

    def capacity(args: dict[str, Any]) -> dict[str, Any]:
        targets = args.get("instance_ids") or []
        return {
            "targets": {i: cloud.instances[i]["state"] for i in targets if i in cloud.instances},
            "running_instances": sum(
                1
                for i in cloud.instances.values()
                if i["service"] == SERVICE and i["state"] == "running"
            ),
        }

    reg.register(
        ToolSpec(
            "cloudwatch.get_log_events",
            lambda log_group, limit=20, contains=None: cloud.get_log_events(
                log_group, contains=contains, limit=limit
            ),
            "Read recent log events (CloudWatch-like).",
            "aws",
            args_model=GetLogs,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.describe_instances",
            lambda service: cloud.describe_instances(service),
            "List instances of a service with their aggregated status checks.",
            "aws",
            args_model=Service,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.get_instance_status",
            lambda instance_id: cloud.get_instance_status(instance_id),
            "Probe one instance directly (fresh status).",
            "aws",
            args_model=InstanceId,
        )
    )
    reg.register(
        ToolSpec(
            "deploy.get_status",
            lambda service: cloud.get_deployment(service),
            "Current and previous deployment for a service.",
            "aws",
            args_model=Service,
        )
    )
    reg.register(
        ToolSpec(
            "lambda.invoke",
            lambda function, payload=None: cloud.invoke(function, payload or {}),
            "Invoke a diagnostic function (Lambda-like).",
            "aws",
            args_model=InvokeFn,
        )
    )
    reg.register(
        ToolSpec(
            "iam.simulate_permission",
            lambda action, resource="*": cloud.simulate_permission(AGENT_ROLE, action, resource),
            "Check whether the agent role may perform an action.",
            "aws",
            args_model=SimulatePermission,
        )
    )
    reg.register(
        ToolSpec(
            "ec2.terminate_instances",
            lambda instance_ids, reason: cloud.terminate_instances(AGENT_ROLE, instance_ids),
            "Terminate instances (destructive).",
            "aws",
            destructive=True,
            args_model=Terminate,
            observe=capacity,
        )
    )
    reg.register(
        ToolSpec(
            "deploy.rollback",
            lambda service, reason: cloud.rollback(AGENT_ROLE, service),
            "Roll a service back to its previous version (destructive).",
            "aws",
            destructive=True,
            args_model=Rollback,
        )
    )
    reg.register(
        ToolSpec(
            "change.propose",
            lambda **p: cloud.propose_change(AGENT_ROLE, **p),
            "File a change proposal for human approval (no infrastructure change).",
            "agent",
            args_model=ProposeChange,
        )
    )
    return reg
