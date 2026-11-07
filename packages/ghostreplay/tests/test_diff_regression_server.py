"""Diff engine, regression generation/reporting and the HTTP API."""

from __future__ import annotations

import json
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from ghostreplay.diff import diff_executions
from ghostreplay.models import FaultSpec, FaultTarget
from ghostreplay.regression import (
    load_case,
    reports_to_json,
    reports_to_junit,
    run_case,
    write_case,
)
from ghostreplay.server import create_app

FAULT = FaultSpec(id="f1", kind="timeout_after_commit", target=FaultTarget(name="bank.withdraw"))


def test_diff_identifies_first_divergence_and_changes(lab):
    base = lab.record("toy-bank", "naive")
    naive = lab.counterfactual(base.id, [FAULT])
    safe = lab.counterfactual(base.id, [FAULT], variant="safe")
    d = diff_executions(naive, safe)
    assert not d.identical
    first = d.rows[d.first_divergence["row"]]
    assert first.a.name == "bank.withdraw" and first.status == "changed"
    types = {e.type for e in d.entries}
    assert "changed_args" in types  # idempotency_key added by the fix
    arg_entry = next(e for e in d.entries if e.type == "changed_args")
    assert any(c["path"] == "idempotency_key" and c["op"] == "added" for c in arg_entry.changes)
    assert d.behavior.tool_counts["bank.withdraw"][0] >= 2
    inv = {i["id"]: i for i in d.behavior.invariants}
    assert inv["bank.no_double_withdrawal"] == {
        "id": "bank.no_double_withdrawal",
        "a": "failed",
        "b": "passed",
        "changed": True,
    }


def test_diff_added_and_removed_calls(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(
        base.id,
        [FaultSpec(id="x", kind="http_500", target=FaultTarget(name="bank.balance"))],
        mode="branch",
    )
    d = diff_executions(base, cf)
    assert any(e.type == "removed_call" and e.name == "bank.withdraw" for e in d.entries)
    assert d.behavior.destructive_calls == (1, 0)


def test_case_generation_runs_and_reports(lab, tmp_path):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(base.id, [FAULT])
    naive_case = lab.case_from_execution(cf.id)
    safe_case = lab.case_from_execution(cf.id, variant="safe")
    assert naive_case.expect == "fail" and safe_case.expect == "pass"
    case_path, test_path = write_case(safe_case, tmp_path)
    src = test_path.read_text()
    compile(src, str(test_path), "exec")  # valid Python
    assert "run_case(load_case(CASE_FILE))" in src
    reports = [run_case(load_case(case_path)), run_case(naive_case)]
    assert reports[0].passed and reports[0].outcome_matches_expectation
    assert not reports[1].passed and reports[1].outcome_matches_expectation
    assert "bank.no_double_withdrawal" in reports[1].explain()
    j = json.loads(reports_to_json(reports))
    assert j["total"] == 2 and j["passed"] == 2
    root = ET.fromstring(reports_to_junit(reports))
    assert root.get("tests") == "2" and root.get("failures") == "0"


def test_http_api_end_to_end(lab):
    client = TestClient(create_app(lab))
    assert client.get("/api/info").json()["app"] == "toy"
    sc = client.get("/api/scenarios").json()[0]
    assert sc["id"] == "toy-bank" and sc["tools"]
    rec = client.post("/api/runs/record", json={"scenario": "toy-bank", "variant": "naive"}).json()
    detail = client.get(f"/api/executions/{rec['id']}").json()
    assert detail["events"][0]["kind"] == "execution_start"
    rp = client.post("/api/runs/replay", json={"execution_id": rec["id"]}).json()
    assert rp["diff"]["identical"] is True
    cf = client.post(
        "/api/runs/counterfactual",
        json={"execution_id": rec["id"], "preset": "withdraw-timeout-after-commit"},
    ).json()
    assert cf["execution"]["mode"] == "branch"
    assert "bank.no_double_withdrawal" in cf["execution"]["failed_invariants"]
    reports = client.post(
        "/api/regression/run", json={"execution_id": cf["execution"]["id"]}
    ).json()
    assert {r["variant"]: r["passed"] for r in reports} == {"naive": False, "safe": True}
    exported = client.post(
        "/api/regression/export", json={"execution_id": cf["execution"]["id"], "variant": "safe"}
    ).json()
    assert exported["test_file"].startswith("test_") and "def test_" in exported["pytest_source"]
    assert client.get("/api/executions/does-not-exist").status_code == 404
    bad = client.post("/api/runs/record", json={"scenario": "toy-bank", "variant": "nope"})
    assert bad.status_code == 400


def test_replay_stream_emits_engine_events(lab):
    client = TestClient(create_app(lab))
    rec = lab.record("toy-bank", "naive")
    with client.stream("GET", f"/api/executions/{rec.id}/replay/stream?delay_ms=0") as resp:
        body = "".join(resp.iter_text())
    names = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert names[0] == "start" and names[-1] == "done"
    assert names.count("event") == len(rec.events)


def test_demo_story(lab):
    story = lab.prepare_demo("toy-bank")
    verdicts = {s.id: s.verdict for s in story.steps}
    assert verdicts == {
        "incident": "fail",
        "replay": "pass",
        "explain": "info",
        "counterfactual": "fail",
        "fix": "pass",
        "prove": "pass",
    }
