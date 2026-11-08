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


# -- the real refund service (HTTP + SQLite) the fix relies on ------------------------------

BODY = {
    "payment_id": "pay_3KQ81",
    "amount_cents": 12900,
    "reason": "damaged_on_arrival",
    "sku": "AUR-EB-01",
}


@pytest.fixture
def world():
    from ghostreplay.core.clock import VirtualClock
    from support_agent.environment import SupportWorld

    w = SupportWorld(VirtualClock())
    yield w
    w.close()


def _committed(w) -> list[tuple]:
    """Read the ledger through a separate SQLite connection: what is really committed."""
    import sqlite3

    with sqlite3.connect(w.db_path) as conn:
        return conn.execute(
            "SELECT id, amount_cents, idempotency_key FROM refunds ORDER BY seq"
        ).fetchall()


def test_refund_requests_really_travel_over_http_and_commit_in_sqlite(world):
    refund = world.post_refund(BODY)
    assert refund["id"] == "re_0001" and refund["amount_cents"] == 12900
    assert world.service.requests == [{"method": "POST", "path": "/v1/refunds", "status": 201}]
    assert _committed(world) == [("re_0001", 12900, None)]
    listed = world.get_refunds("pay_3KQ81")
    assert listed["count"] == 1 and listed["data"][0]["id"] == "re_0001"


def test_retry_without_idempotency_key_creates_a_duplicate_refund(world):
    world.post_refund(BODY)
    world.post_refund(BODY)
    assert [r[1] for r in _committed(world)] == [12900, 12900]


def test_retry_with_same_idempotency_key_returns_the_original_refund(world):
    first = world.post_refund(BODY, "refund:T-1:pay_3KQ81:12900")
    again = world.post_refund(BODY, "refund:T-1:pay_3KQ81:12900")
    assert again["id"] == first["id"] and again["idempotent_replayed"] is True
    assert len(_committed(world)) == 1
    outcomes = [a["outcome"] for a in world.snapshot()["refund_attempts"]]
    assert outcomes == ["committed", "idempotent_replay"]


def test_reusing_idempotency_key_with_different_amount_is_rejected(world):
    from ghostreplay import HttpError

    world.post_refund(BODY, "k-1")
    with pytest.raises(HttpError) as info:
        world.post_refund({**BODY, "amount_cents": 100}, "k-1")
    assert info.value.data["status"] == 409
    assert len(_committed(world)) == 1


def test_service_never_refunds_more_than_was_captured(world):
    from ghostreplay import HttpError

    world.post_refund({**BODY, "amount_cents": 28800})
    with pytest.raises(HttpError) as info:
        world.post_refund({**BODY, "amount_cents": 1})
    assert info.value.data["status"] == 400
    assert sum(r[1] for r in _committed(world)) == 28800


def test_timeout_after_commit_really_commits_before_the_client_times_out():
    from ghostreplay import ToolTimeout
    from ghostreplay.core.clock import VirtualClock
    from support_agent.environment import SupportWorld

    w = SupportWorld(VirtualClock(), payment_gateway="timeout_after_commit")
    try:
        with pytest.raises(ToolTimeout):
            w.post_refund(BODY)
        # The client saw a timeout, but the transaction is committed in the database.
        assert len(_committed(w)) == 1
        assert [a["action"] for a in w.snapshot()["audit_events"]] == [
            "refund.committed",
            "response.delayed_after_commit",
        ]
    finally:
        w.close()


def test_replaying_the_duplicate_refund_starts_no_service_and_writes_no_database(lab, monkeypatch):
    import support_agent.environment as env_mod
    from ghostreplay import labkit

    incident = lab.record(SC, "vulnerable", conditions={"payment_gateway": "timeout_after_commit"})
    assert incident.final_state["payments"]["total_refunded_cents"] == 25800

    def forbidden(*_a, **_k):
        raise AssertionError("a real world, HTTP request or database was used during replay")

    monkeypatch.setattr(env_mod.SupportWorld, "__init__", forbidden)
    monkeypatch.setattr(labkit, "http_json", forbidden)
    monkeypatch.setattr(env_mod, "http_json", forbidden)
    rpl = lab.replay(incident.id)
    assert rpl.status == ExecutionStatus.COMPLETED
    assert diff_executions(incident, rpl).identical
    creates = [e for e in rpl.events if e.name == "payments.create_refund"]
    assert len(creates) == 2 and all(e.source == EventSource.RECORDED for e in creates)
