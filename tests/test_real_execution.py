"""Real execution: HTTP services, SQLite state, the capture library and re-execution.

These tests use the scripted model (no API key needed) or the genuine captures shipped with
the labs. The live-provider test lives in ``tests/live/`` and only runs when explicitly enabled.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from devops_agent.cli import build_lab as build_devops
from ghostreplay.llm.anthropic_adapter import to_tools
from ghostreplay.server.app import create_app
from ghostreplay.server.settings import ServerSettings
from ghostreplay.storage import OwnershipConflict, SqliteStore
from ghostreplay.storage.library import load_library
from support_agent.cli import build_lab as build_support


@pytest.fixture
def capture_timeout(monkeypatch):
    """Captures were recorded with the production 1200 ms client timeout."""
    import support_agent.environment as env

    monkeypatch.setattr(env, "CLIENT_TIMEOUT_MS", 1200)
    monkeypatch.setattr(env, "COMMIT_DELAY_MS", 2700)


def _support():
    lab = build_support(SqliteStore(":memory:"))
    return lab, lab.scenario("duplicate-refund")


# -- support: real HTTP + SQLite -------------------------------------------------------------


def test_record_mode_sends_real_http_requests_and_commits_sql_rows():
    lab, sc = _support()
    ex = lab.record(sc.id, "vulnerable", conditions=sc.incident_conditions())
    fs = ex.final_state
    assert fs["evidence"]["http_requests_received"] == 2  # two POSTs really reached the service
    assert [a["outcome"] for a in fs["refund_attempts"]] == ["committed", "committed"]
    assert fs["payments"]["total_refunded_cents"] == 25800
    first = next(e for e in ex.events if e.name == "payments.create_refund")
    assert first.error.type == "ToolTimeout" and "no response received" in first.error.message
    assert first.state_before["refund_count"] == 0 and first.state_after["refund_count"] == 1
    actions = [a["action"] for a in fs["audit_events"]]
    assert actions == ["refund.committed", "response.delayed_after_commit", "refund.committed"]


def test_idempotency_prevents_the_duplicate_in_the_database():
    lab, sc = _support()
    ex = lab.record(sc.id, "fixed", conditions=sc.incident_conditions())
    refunds = ex.final_state["payments"]["refunds"]
    assert len(refunds) == 1 and refunds[0]["idempotency_key"].startswith("refund:")
    assert not [i for i in ex.invariants if i.status == "failed"]


def test_strict_replay_makes_no_calls_and_creates_no_world(monkeypatch):
    import support_agent.environment as env
    from ghostreplay import labkit

    lab, sc = _support()
    rec = lab.record(sc.id, "vulnerable", conditions=sc.incident_conditions())

    def forbidden(*_a, **_k):
        raise AssertionError("replay touched a real service or database")

    monkeypatch.setattr(env.SupportWorld, "__init__", forbidden)
    monkeypatch.setattr(labkit.LocalService, "start", forbidden)
    rpl = lab.replay(rec.id)
    assert rpl.status.value == "completed"
    calls = [e for e in rpl.events if e.kind.value in ("tool_call", "model_call")]
    assert calls and all(e.source.value == "recorded" for e in calls)


# -- devops: the isolated lab ----------------------------------------------------------------


def test_devops_lab_is_real_isolated_and_allowlisted():
    from devops_agent.environment import build_cloud
    from devops_agent.lab import InfraLab
    from ghostreplay.core.clock import VirtualClock
    from ghostreplay.labkit import http_json

    lab = InfraLab(build_cloud(VirtualClock(), health_checks="stale"))
    try:
        assert all(
            s.url.startswith("http://127.0.0.1:") for s in [lab.controller, *lab.instances.values()]
        )
        monitoring = lab.get("/v1/instances?service=checkout-api")
        assert {i["status_check"] for i in monitoring} == {"impaired"}  # stale view (the fault)
        iid = monitoring[0]["instance_id"]
        assert lab.get(f"/v1/instances/{iid}/status")["status_check"] == "ok"  # real probe
        with pytest.raises(Exception, match="404"):
            http_json(
                "POST", f"{lab.controller.url}/v1/shell", service="c", json_body={"cmd": "ls"}
            )
        lab.post("/v1/instances/terminate", {"instance_ids": [iid], "reason": "test"})
        assert not lab.instances[iid].running  # the service was really shut down
        assert lab.probe(iid)["status"] == "unreachable"
        assert lab.get(f"/v1/instances/{iid}/status")["state"] == "terminated"
    finally:
        lab.close()


def test_devops_replay_starts_no_lab(monkeypatch):
    from devops_agent import lab as lab_mod

    lab = build_devops(SqliteStore(":memory:"))
    sc = lab.scenario("unsafe-infra-action")
    rec = lab.record(sc.id, "vulnerable", conditions=sc.incident_conditions())
    monkeypatch.setattr(
        lab_mod.InfraLab,
        "__init__",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("lab started")),
    )
    assert lab.replay(rec.id).status.value == "completed"


# -- the genuine capture library -------------------------------------------------------------


def test_library_contains_genuine_live_captures():
    store = SqliteStore(":memory:")
    lab = build_support(store)
    ids = load_library(store, lab.library_dir)
    assert len(ids) == 2
    for cid in ids:
        ex = store.get(cid)
        assert ex.provenance.model_is_live and ex.provenance.model_provider == "anthropic"
        models = [e for e in ex.events if e.kind.value == "model_call"]
        assert models and all(e.source.value == "live" for e in models)
        assert all(e.response.get("served_by") for e in models)
        # Tool decisions came from the model: every tool call answers a model tool_use.
        requested = {c["name"] for e in models for c in e.response.get("tool_calls", [])}
        assert "payments.create_refund" in requested
        # No readable private reasoning is stored (only opaque signatures, if any).
        for e in models:
            for b in e.response.get("provider_content") or []:
                if b.get("type") == "thinking":
                    assert b.get("thinking", "") == ""
    assert load_library(store, lab.library_dir) == ids  # idempotent


def test_reexecuting_the_buggy_capture_duplicates_the_refund_again_without_the_model(
    capture_timeout,
):
    store = SqliteStore(":memory:")
    lab = build_support(store)
    assert lab.live is None
    ids = load_library(store, lab.library_dir)
    buggy = next(i for i in ids if store.get(i).variant == "vulnerable")
    again = lab.reexecute(buggy)
    assert again.status.value == "completed" and again.divergence is None
    model = [e for e in again.events if e.kind.value == "model_call"]
    assert model and all(e.source.value == "recorded" for e in model)  # no provider call
    tools = [e for e in again.events if e.kind.value == "tool_call"]
    assert tools and all(e.source.value == "simulated" for e in tools)  # executed now, for real
    assert again.final_state["payments"]["total_refunded_cents"] == 25800
    assert again.final_state["evidence"]["http_requests_received"] >= 2


def test_library_rows_are_shared_read_only_and_never_expire():
    store = SqliteStore(":memory:", owner_ttl_s=1)
    lab = build_support(store)
    ids = load_library(store, lab.library_dir)
    visitor = store.scoped("visitor-1")
    assert {s.id for s in visitor.list()} >= set(ids)
    ex = visitor.get(ids[0])
    with pytest.raises(OwnershipConflict):
        visitor.save(ex)
    assert store.expire(now=10**12) == 0
    assert store.delete_all() == 0
    assert set(store.library_ids()) == set(ids)
    assert all(store.get(i) for i in ids)


def test_public_api_exposes_library_and_reexecution(capture_timeout):
    settings = ServerSettings.from_env(
        {"GHOSTREPLAY_PUBLIC": "1", "GHOSTREPLAY_INSECURE_COOKIES": "1"}
    )
    client = TestClient(create_app(build_support(SqliteStore(":memory:")), settings=settings))
    lib = client.get("/api/library").json()
    assert len(lib["captures"]) == 2 and lib["manifest"]["provider"] == "anthropic"
    fixed = next(c for c in lib["captures"] if c["variant"] == "fixed")
    r = client.post("/api/runs/reexecute", json={"execution_id": fixed["id"]})
    assert r.status_code == 200, r.text
    run = client.get(f"/api/executions/{r.json()['execution']['id']}").json()
    assert run["final_state"]["payments"]["total_refunded_cents"] == 12900
    assert "genuine capture" in run["provenance"]["label"]
    reports = client.post(
        "/api/regression/run", json={"execution_id": fixed["id"], "variants": ["fixed"]}
    ).json()
    assert reports[0]["passed"] is True and reports[0]["outcome_matches_expectation"] is True


def test_adapter_sends_tool_parameters_to_the_model():
    tools = to_tools(
        [
            {
                "name": "orders.lookup",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}},
            }
        ]
    )
    assert tools[0]["name"] == "orders__lookup"
    assert tools[0]["input_schema"]["properties"] == {"order_id": {"type": "string"}}


def test_capture_files_are_valid_redacted_traces():
    from pathlib import Path

    for f in Path("apps").glob("*/src/*/captures/*.trace.json"):
        raw = f.read_text()
        assert "sk-ant-" not in raw and "ANTHROPIC_API_KEY" not in raw
        assert json.loads(raw)["schema_version"] == "ghostreplay/v1"
