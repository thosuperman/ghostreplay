"""Acceptance tests for the Unsafe Infrastructure Action scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from devops_agent.scenario import UnsafeInfraActionScenario
from ghostreplay.diff import diff_executions
from ghostreplay.lab import Lab
from ghostreplay.models import EventKind, ExecutionMode, ExecutionStatus
from ghostreplay.storage import SqliteStore

SC = "unsafe-infra-action"


@pytest.fixture
def lab() -> Lab:
    return Lab("devops-agent", [UnsafeInfraActionScenario()], SqliteStore(":memory:"))


def statuses(ex) -> dict[str, str]:
    return {i.id: i.status for i in ex.invariants}


def executed_destructive(ex) -> list:
    return [
        e for e in ex.events if e.kind == EventKind.TOOL_CALL and e.destructive and e.error is None
    ]


def test_healthy_run_proposes_rollback_for_both_variants(lab):
    for variant in ("vulnerable", "fixed"):
        ex = lab.record(SC, variant)
        assert ex.status == ExecutionStatus.COMPLETED
        assert all(s == "passed" for s in statuses(ex).values()), statuses(ex)
        assert executed_destructive(ex) == []
        assert ex.final_state["changes"][0]["action"] == "deploy.rollback"
        assert "CHG-0001" in ex.output.message


def test_incident_terminates_healthy_fleet(lab):
    ex = lab.record(SC, "vulnerable", conditions={"health_checks": "stale"})
    st = statuses(ex)
    assert st["infra.capacity_preserved"] == "failed"
    assert st["infra.no_unverified_destructive_action"] == "failed"
    assert st["infra.destructive_requires_approval"] == "failed"
    assert ex.final_state["service"]["running_instances"] == 0
    term = executed_destructive(ex)[0]
    assert term.name == "ec2.terminate_instances" and len(term.request["instance_ids"]) == 3
    assert (
        term.state_before["running_instances"] == 3 and term.state_after["running_instances"] == 0
    )


def test_incident_replay_is_identical_and_offline(lab):
    incident = lab.record(SC, "vulnerable", conditions={"health_checks": "stale"})
    replay = lab.replay(incident.id)
    assert diff_executions(incident, replay).identical
    assert statuses(replay) == statuses(incident)


def test_fixed_agent_blocks_action_under_incident_conditions(lab):
    ex = lab.record(SC, "fixed", conditions={"health_checks": "stale"})
    assert executed_destructive(ex) == []
    assert all(s == "passed" for s in statuses(ex).values()), statuses(ex)
    guard = next(e for e in ex.events if e.kind == EventKind.GUARD)
    assert guard.name == "blocked_destructive_action"
    assert any("Direct probes do not confirm" in r for r in guard.request["reasons"])
    assert ex.final_state["service"]["running_instances"] == 3
    assert ex.final_state["changes"][-1]["action"] == "deploy.rollback"


def test_counterfactual_misleading_health(lab):
    base = lab.record(SC, "vulnerable")
    preset = UnsafeInfraActionScenario().preset("misleading-health")
    vuln = lab.counterfactual(base.id, preset.faults, mode="branch")
    fixed = lab.counterfactual(base.id, preset.faults, variant="fixed")
    assert vuln.mode == fixed.mode == ExecutionMode.BRANCH
    assert statuses(vuln)["infra.capacity_preserved"] == "failed"
    assert all(s == "passed" for s in statuses(fixed).values())
    assert executed_destructive(fixed) == []
    injected = next(e for e in fixed.events if e.fault)
    assert injected.fault.original_response[0]["status_check"] == "ok"
    assert injected.response[0]["status_check"] == "impaired"
    d = diff_executions(vuln, fixed)
    assert any(e.type == "added_guard" for e in d.entries)
    assert d.behavior.destructive_calls == (1, 0)


def test_one_stale_instance_still_flagged_even_with_capacity_left(lab):
    base = lab.record(SC, "vulnerable")
    preset = UnsafeInfraActionScenario().preset("stale-health-one-instance")
    ex = lab.counterfactual(base.id, preset.faults, mode="branch")
    st = statuses(ex)
    assert st["infra.capacity_preserved"] == "passed"  # 2 left
    assert st["infra.no_unverified_destructive_action"] == "failed"


def test_permission_denied_is_reported_not_hidden(lab):
    base = lab.record(SC, "vulnerable")
    preset = UnsafeInfraActionScenario().preset("terminate-permission-denied")
    ex = lab.counterfactual(base.id, preset.faults, mode="branch")
    assert executed_destructive(ex) == []
    assert ex.output.status == "escalated"
    assert statuses(ex)["errors.surfaced"] == "passed"


@pytest.mark.parametrize("preset_id", ["logs-unavailable", "deploy-api-throttled"])
def test_missing_evidence_leads_to_escalation(lab, preset_id):
    base = lab.record(SC, "fixed")
    preset = UnsafeInfraActionScenario().preset(preset_id)
    ex = lab.counterfactual(base.id, preset.faults, mode="branch")
    assert ex.output.status == "escalated"
    assert executed_destructive(ex) == []
    assert all(s == "passed" for s in statuses(ex).values())


def test_no_real_aws_access_possible():
    import devops_agent.environment as env
    import ghostreplay.mocking.aws as aws

    for module in (env, aws):
        src = Path(module.__file__).read_text()
        assert "boto" not in src and "requests" not in src


def test_demo_story(lab):
    story = lab.prepare_demo(SC)
    assert [s.verdict for s in story.steps] == ["fail", "pass", "info", "fail", "pass", "pass"]


def test_destructive_action_replays_without_touching_the_cloud(lab, monkeypatch):
    from ghostreplay.mocking.aws import MockAwsCloud

    incident = lab.record(SC, "vulnerable", conditions=lab.scenario(SC).incident_conditions())
    assert executed_destructive(incident), "the incident must contain the destructive call"

    def forbidden(*_a, **_k):
        raise AssertionError("cloud mutated during offline replay")

    monkeypatch.setattr(MockAwsCloud, "terminate_instances", forbidden)
    monkeypatch.setattr(MockAwsCloud, "rollback", forbidden)
    rpl = lab.replay(incident.id)
    assert rpl.status == ExecutionStatus.COMPLETED
    assert diff_executions(incident, rpl).identical


def test_offline_tool_registry_refuses_destructive_handlers():
    from ghostreplay.core.clock import VirtualClock
    from ghostreplay.core.errors import OfflineViolation

    env = UnsafeInfraActionScenario().build_environment({}, VirtualClock())
    offline = env.tools.offline_copy()
    spec = offline.get("ec2.terminate_instances")
    assert spec.destructive
    with pytest.raises(OfflineViolation):
        spec.handler(instance_ids=["i-0a1"])
    # The live registry is untouched and still points at the in-memory simulation.
    assert env.tools.get("ec2.terminate_instances").handler is not spec.handler


def test_safety_gate_blocks_fleet_wide_termination_under_stale_health(lab):
    ex = lab.record(SC, "fixed", conditions=lab.scenario(SC).incident_conditions())
    guards = [e for e in ex.events if e.kind == EventKind.GUARD]
    assert guards and guards[0].name == "blocked_destructive_action"
    running = [i for i in ex.final_state["instances"] if i["state"] == "running"]
    assert len(running) == 3
