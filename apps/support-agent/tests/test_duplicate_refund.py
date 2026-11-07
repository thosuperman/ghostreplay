"""Acceptance tests for the Duplicate Refund scenario."""

from __future__ import annotations

import pytest

from ghostreplay.diff import diff_executions
from ghostreplay.lab import Lab
from ghostreplay.models import EventKind, EventSource, ExecutionMode, ExecutionStatus
from ghostreplay.storage import SqliteStore
from support_agent.scenario import DuplicateRefundScenario

SC = "duplicate-refund"


@pytest.fixture
def lab() -> Lab:
    return Lab("support-agent", [DuplicateRefundScenario()], SqliteStore(":memory:"))


def statuses(ex) -> dict[str, str]:
    return {i.id: i.status for i in ex.invariants}


def refunds(ex) -> list[dict]:
    return ex.final_state["payments"]["refunds"]


def test_healthy_run_passes_for_both_variants(lab):
    for variant in ("vulnerable", "fixed"):
        ex = lab.record(SC, variant)
        assert ex.status == ExecutionStatus.COMPLETED
        assert ex.output.status == "success"
        assert len(refunds(ex)) == 1 and refunds(ex)[0]["amount_cents"] == 12900
        assert all(s == "passed" for s in statuses(ex).values()), statuses(ex)
        tools = [e.name for e in ex.events if e.kind == EventKind.TOOL_CALL]
        assert tools == [
            "orders.lookup_order",
            "refunds.check_eligibility",
            "payments.create_refund",
            "crm.send_reply",
        ]


def test_incident_reproduces_duplicate_refund(lab):
    ex = lab.record(SC, "vulnerable", conditions={"payment_gateway": "timeout_after_commit"})
    st = statuses(ex)
    assert st["refund.no_duplicate"] == "failed"
    assert st["refund.retries_are_idempotent"] == "failed"
    assert st["reply.matches_ledger"] == "failed"
    assert [r["id"] for r in refunds(ex)] == ["re_0001", "re_0002"]
    calls = [e for e in ex.events if e.name == "payments.create_refund"]
    assert [c.error.type if c.error else None for c in calls] == ["ToolTimeout", None]
    assert calls[0].state_after["refund_count"] == 1  # committed despite the timeout
    assert any(e.kind == EventKind.AGENT_STEP and e.name == "retry" for e in ex.events)


def test_incident_replays_offline_identically(lab):
    incident = lab.record(SC, "vulnerable", conditions={"payment_gateway": "timeout_after_commit"})
    replay = lab.replay(incident.id)
    assert replay.status == ExecutionStatus.COMPLETED
    assert diff_executions(incident, replay).identical
    assert statuses(replay) == statuses(incident)
    assert {e.source for e in replay.events if e.is_interaction} == {EventSource.RECORDED}


def test_fixed_agent_survives_incident_conditions(lab):
    ex = lab.record(SC, "fixed", conditions={"payment_gateway": "timeout_after_commit"})
    assert len(refunds(ex)) == 1
    assert all(s == "passed" for s in statuses(ex).values()), statuses(ex)
    names = [e.name for e in ex.events if e.kind in (EventKind.TOOL_CALL, EventKind.AGENT_STEP)]
    assert "payments.list_refunds" in names and "recovered" in names


def test_counterfactual_fails_vulnerable_and_passes_fixed(lab):
    base = lab.record(SC, "vulnerable")
    preset = DuplicateRefundScenario().preset("refund-timeout-after-commit")
    vuln = lab.counterfactual(base.id, preset.faults)
    fixed = lab.counterfactual(base.id, preset.faults, variant="fixed")
    assert vuln.mode == fixed.mode == ExecutionMode.BRANCH
    assert statuses(vuln)["refund.no_duplicate"] == "failed"
    assert len(refunds(vuln)) == 2
    assert statuses(fixed)["refund.no_duplicate"] == "passed"
    assert len(refunds(fixed)) == 1
    d = diff_executions(vuln, fixed)
    first = d.rows[d.first_divergence["row"]]
    assert first.a.name == "payments.create_refund"
    assert d.behavior.final_state_changes  # the ledger differs


def test_timeout_before_commit_hides_the_bug(lab):
    """The same retry logic is 'safe by luck' when nothing was committed."""
    base = lab.record(SC, "vulnerable")
    preset = DuplicateRefundScenario().preset("refund-timeout-before-commit")
    ex = lab.counterfactual(base.id, preset.faults, mode="branch")
    assert len(refunds(ex)) == 1
    assert statuses(ex)["refund.no_duplicate"] == "passed"
    assert statuses(ex)["refund.retries_are_idempotent"] == "failed"  # still flagged


@pytest.mark.parametrize(
    "preset_id",
    [
        "gateway-down",
        "eligibility-missing-amount",
        "order-lookup-unauthorized",
        "gateway-rate-limited",
    ],
)
def test_other_presets_are_handled_safely_by_fixed_agent(lab, preset_id):
    base = lab.record(SC, "fixed")
    preset = DuplicateRefundScenario().preset(preset_id)
    ex = lab.counterfactual(base.id, preset.faults, mode="branch")
    assert ex.status == ExecutionStatus.COMPLETED
    st = statuses(ex)
    assert st["refund.no_duplicate"] == "passed"
    assert st["errors.surfaced"] == "passed"
    assert st["reply.matches_ledger"] == "passed", ex.final_state["outbox"]
    if preset_id != "gateway-rate-limited":
        assert ex.output.status == "escalated"
        assert refunds(ex) == []


def test_strict_counterfactual_does_not_invent_continuation(lab):
    base = lab.record(SC, "vulnerable")
    preset = DuplicateRefundScenario().preset("gateway-down")
    ex = lab.counterfactual(base.id, preset.faults, mode="replay")
    assert ex.mode == ExecutionMode.COUNTERFACTUAL_REPLAY
    assert ex.status == ExecutionStatus.DIVERGED
    assert ex.divergence.after_fault
    assert statuses(ex)["refund.no_duplicate"] == "inconclusive"


def test_demo_story(lab):
    story = lab.prepare_demo(SC)
    assert [s.verdict for s in story.steps] == ["fail", "pass", "info", "fail", "pass", "pass"]
    assert all(r.outcome_matches_expectation for r in story.reports)


def test_cli_run_exit_codes(tmp_path):
    from support_agent.cli import main

    assert main(["--db", str(tmp_path), "run", "--variant", "fixed", "--incident"]) == 0
    assert main(["--db", str(tmp_path), "run", "--variant", "vulnerable", "--incident"]) == 1
