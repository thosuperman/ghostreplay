"""A simulated, in-memory AWS-like cloud. It never imports an AWS SDK or reads credentials.

Resources: EC2-like instances (with an aggregated health view that can lag behind direct
probes), CloudWatch-like log groups, Lambda-like functions (simulated Python callables),
deployments, an IAM-like permission model and change proposals. Every mutating call is
permission-checked and written to an audit log.
"""

from __future__ import annotations

import copy
import fnmatch
from collections.abc import Callable
from typing import Any

from ..core.clock import Clock
from ..core.errors import PermissionDenied, ToolError, register_error_type


@register_error_type
class ResourceNotFound(ToolError):
    error_type = "ResourceNotFound"


@register_error_type
class InvalidState(ToolError):
    error_type = "InvalidState"


class MockAwsCloud:
    def __init__(
        self, clock: Clock, *, account_id: str = "000000000000", region: str = "us-east-1"
    ):
        self.clock = clock
        self.account_id = account_id
        self.region = region
        self.instances: dict[str, dict[str, Any]] = {}
        self._aggregated_status: dict[str, str] = {}  # stale health-view overrides
        self.log_groups: dict[str, list[dict[str, Any]]] = {}
        self.functions: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self.deployments: dict[str, dict[str, Any]] = {}
        self.permissions: dict[str, list[str]] = {}
        self.changes: dict[str, dict[str, Any]] = {}
        self.audit_log: list[dict[str, Any]] = []

    # -- fixtures ---------------------------------------------------------------------
    def add_instance(self, instance_id: str, *, service: str, health: str = "ok", **extra: Any):
        self.instances[instance_id] = {
            "instance_id": instance_id,
            "service": service,
            "state": "running",
            "health": health,
            **extra,
        }

    def set_aggregated_status(self, instance_id: str, status: str) -> None:
        """Make the aggregated health view report ``status`` (e.g. a stale 'impaired')."""
        self._aggregated_status[instance_id] = status

    def add_log_events(self, group: str, events: list[dict[str, Any]]) -> None:
        self.log_groups.setdefault(group, []).extend(copy.deepcopy(events))

    def add_function(self, name: str, fn: Callable[[dict[str, Any]], Any]) -> None:
        self.functions[name] = fn

    def set_deployment(self, service: str, **info: Any) -> None:
        self.deployments[service] = copy.deepcopy(info)

    def grant(self, principal: str, *actions: str) -> None:
        self.permissions.setdefault(principal, []).extend(actions)

    # -- read operations ----------------------------------------------------------------
    def describe_instances(self, service: str) -> list[dict[str, Any]]:
        self.clock.advance(120)
        out = []
        for inst in sorted(self.instances.values(), key=lambda i: i["instance_id"]):
            if inst["service"] != service:
                continue
            view = {k: v for k, v in inst.items() if k != "health"}
            view["status_check"] = (
                "n/a"
                if inst["state"] != "running"
                else self._aggregated_status.get(inst["instance_id"], inst["health"])
            )
            view["status_source"] = "aggregated-health-view"
            out.append(view)
        return out

    def get_instance_status(self, instance_id: str) -> dict[str, Any]:
        """Direct probe of one instance (always current)."""
        self.clock.advance(250)
        inst = self._instance(instance_id)
        return {
            "instance_id": instance_id,
            "state": inst["state"],
            "status_check": inst["health"] if inst["state"] == "running" else "n/a",
            "status_source": "direct-probe",
            "checked_at": self.clock.now().isoformat(),
        }

    def get_log_events(self, group: str, *, contains: str | None = None, limit: int = 20):
        self.clock.advance(180)
        if group not in self.log_groups:
            raise ResourceNotFound(f"log group {group} not found", data={"group": group})
        events = [
            e
            for e in self.log_groups[group]
            if contains is None or contains in e.get("message", "")
        ]
        return {"group": group, "events": copy.deepcopy(events[-limit:]), "total": len(events)}

    def get_deployment(self, service: str) -> dict[str, Any]:
        self.clock.advance(90)
        if service not in self.deployments:
            raise ResourceNotFound(f"no deployment for {service}", data={"service": service})
        return copy.deepcopy(self.deployments[service])

    def invoke(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.clock.advance(400)
        if function not in self.functions:
            raise ResourceNotFound(f"function {function} not found", data={"function": function})
        return {
            "function": function,
            "status_code": 200,
            "payload": self.functions[function](payload),
        }

    def simulate_permission(
        self, principal: str, action: str, resource: str = "*"
    ) -> dict[str, Any]:
        self.clock.advance(60)
        allowed = self._allowed(principal, action)
        return {
            "principal": principal,
            "action": action,
            "resource": resource,
            "decision": "allowed" if allowed else "implicitDeny",
        }

    # -- mutating operations --------------------------------------------------------------
    def terminate_instances(self, principal: str, instance_ids: list[str]) -> dict[str, Any]:
        self._require(principal, "ec2:TerminateInstances")
        self.clock.advance(800)
        changed = []
        for iid in instance_ids:
            inst = self._instance(iid)
            if inst["state"] == "terminated":
                continue
            previous = inst["state"]
            inst["state"] = "terminated"
            changed.append(
                {"instance_id": iid, "previous_state": previous, "current_state": "terminated"}
            )
        self._audit(principal, "ec2:TerminateInstances", {"instance_ids": instance_ids})
        return {"terminating_instances": changed}

    def rollback(self, principal: str, service: str) -> dict[str, Any]:
        self._require(principal, "deploy:Rollback")
        self.clock.advance(1500)
        dep = self.deployments.get(service)
        if not dep or not dep.get("previous_version"):
            raise InvalidState(f"{service} has no previous version", data={"service": service})
        dep["current_version"], dep["previous_version"] = (
            dep["previous_version"],
            dep["current_version"],
        )
        dep["status"] = "rolled_back"
        self._audit(principal, "deploy:Rollback", {"service": service})
        return copy.deepcopy(dep)

    def propose_change(self, principal: str, **proposal: Any) -> dict[str, Any]:
        self.clock.advance(70)
        change_id = f"CHG-{len(self.changes) + 1:04d}"
        record = {
            "change_id": change_id,
            "status": "pending_approval",
            "requested_by": principal,
            "created_at": self.clock.now().isoformat(),
            **copy.deepcopy(proposal),
        }
        self.changes[change_id] = record
        self._audit(principal, "change:Propose", {"change_id": change_id})
        return copy.deepcopy(record)

    def approve_change(self, change_id: str, approver: str) -> None:
        """Human approval (never exposed as an agent tool)."""
        self.changes[change_id]["status"] = "approved"
        self.changes[change_id]["approved_by"] = approver

    # -- state ------------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "instances": [copy.deepcopy(self.instances[k]) for k in sorted(self.instances)],
            "deployments": copy.deepcopy(self.deployments),
            "changes": [copy.deepcopy(self.changes[k]) for k in sorted(self.changes)],
            "audit_log": copy.deepcopy(self.audit_log),
        }

    # -- helpers ------------------------------------------------------------------------------
    def _instance(self, instance_id: str) -> dict[str, Any]:
        if instance_id not in self.instances:
            raise ResourceNotFound(
                f"instance {instance_id} not found", data={"instance_id": instance_id}
            )
        return self.instances[instance_id]

    def _allowed(self, principal: str, action: str) -> bool:
        return any(fnmatch.fnmatchcase(action, pat) for pat in self.permissions.get(principal, []))

    def _require(self, principal: str, action: str) -> None:
        if not self._allowed(principal, action):
            raise PermissionDenied(
                f"{principal} is not authorized to perform {action}",
                data={"principal": principal, "action": action},
            )

    def _audit(self, principal: str, action: str, detail: dict[str, Any]) -> None:
        self.audit_log.append(
            {"at": self.clock.now().isoformat(), "principal": principal, "action": action, **detail}
        )
