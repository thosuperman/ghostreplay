"""Public deployments: each visitor session only sees and touches its own executions."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from ghostreplay.server.app import SESSION_COOKIE, create_app, session_owner
from ghostreplay.server.settings import ServerSettings
from ghostreplay.storage import OwnershipConflict, SqliteStore
from support_agent.cli import build_lab as build_support_lab

SCENARIO = "duplicate-refund"
PUBLIC = ServerSettings.from_env({"GHOSTREPLAY_PUBLIC": "1"})


@pytest.fixture
def store() -> SqliteStore:
    return SqliteStore(":memory:")


@pytest.fixture
def app(store):
    return create_app(build_support_lab(store), settings=PUBLIC)


def visitor(app) -> TestClient:
    # Session cookies are Secure, so talk to the app over https like a real browser would.
    return TestClient(app, base_url="https://testserver")


def test_public_profile_enables_isolation_and_caps():
    assert PUBLIC.isolate_sessions and PUBLIC.cookie_secure
    assert PUBLIC.session_ttl_s == 24 * 3600
    assert PUBLIC.max_executions_per_session == 80
    assert PUBLIC.max_stream_delay_ms == 400
    assert not PUBLIC.expose_docs
    local = ServerSettings.from_env({})
    assert not local.isolate_sessions and local.expose_docs


def test_session_cookie_is_issued_once_with_safe_attributes(app):
    alice = visitor(app)
    first = alice.get("/api/info")
    cookie = first.headers["set-cookie"].lower()
    for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=86400"):
        assert attr in cookie
    assert first.json()["isolated_sessions"] is True
    assert first.json()["session_ttl_hours"] == 24
    assert "set-cookie" not in alice.get("/api/info").headers  # reused, not reissued


def test_visitors_cannot_see_or_use_each_others_executions(app):
    alice, bob = visitor(app), visitor(app)
    story = alice.post("/api/demo/prepare", json={"scenario": SCENARIO}).json()
    assert story["ok"] is True
    mine = alice.get("/api/executions").json()
    assert len(mine) >= 5
    target = mine[0]["id"]
    other = mine[1]["id"]

    assert bob.get("/api/executions").json() == []
    assert bob.get(f"/api/executions/{target}").status_code == 404
    assert bob.post("/api/runs/replay", json={"execution_id": target}).status_code == 404
    assert bob.get("/api/diff", params={"a": target, "b": other}).status_code == 404
    assert (
        bob.post(
            "/api/runs/counterfactual",
            json={"execution_id": target, "preset": "timeout-after-commit"},
        ).status_code
        == 404
    )
    assert bob.post("/api/regression/export", json={"execution_id": target}).status_code == 404
    assert bob.post("/api/regression/run", json={"execution_id": target}).status_code == 404
    assert bob.get(f"/api/executions/{target}/replay/stream").status_code == 404

    # Alice still has full access to her own runs.
    assert alice.get(f"/api/executions/{target}").status_code == 200
    assert alice.post("/api/runs/replay", json={"execution_id": target}).status_code == 200


def test_a_supplied_case_cannot_overwrite_another_visitors_execution(app, store):
    alice, bob = visitor(app), visitor(app)
    rec = alice.post("/api/runs/record", json={"scenario": SCENARIO, "variant": "vulnerable"})
    rec_id = rec.json()["id"]
    original = store.get(rec_id).model_dump_json()

    case = alice.post(
        "/api/regression/export", json={"execution_id": rec_id, "variant": "vulnerable"}
    ).json()["case"]
    # The exported case for a plain recording has no reference; give it one that reuses
    # Alice's execution id, as a malicious client could.
    case["reference"] = alice.get(f"/api/executions/{rec_id}").json()
    case["reference"].pop("summary")
    case["reference"]["title"] = "overwritten by bob"
    r = bob.post("/api/regression/run", json={"case": case})
    assert r.status_code == 400 and "already in use" in r.json()["detail"]
    assert store.get(rec_id).model_dump_json() == original


def test_store_never_holds_the_raw_session_cookie(app, store):
    alice = visitor(app)
    alice.post("/api/runs/record", json={"scenario": SCENARIO, "variant": "fixed"})
    sid = alice.cookies[SESSION_COOKIE]
    owners = {r[0] for r in store._conn.execute("SELECT owner FROM executions")}
    assert owners == {session_owner(sid)} and sid not in owners


def test_malformed_session_cookie_is_replaced(app):
    client = visitor(app)
    client.cookies.set(SESSION_COOKIE, "../../etc/passwd", domain="testserver")
    r = client.get("/api/executions")
    assert r.status_code == 200 and SESSION_COOKIE in r.headers["set-cookie"]


def test_api_docs_are_not_served_publicly(app):
    client = visitor(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_each_session_keeps_a_bounded_number_of_executions(store):
    settings = ServerSettings.from_env(
        {"GHOSTREPLAY_PUBLIC": "1", "GHOSTREPLAY_MAX_EXECUTIONS_PER_SESSION": "3"}
    )
    client = visitor(create_app(build_support_lab(store), settings=settings))
    for _ in range(5):
        client.post("/api/runs/record", json={"scenario": SCENARIO, "variant": "fixed"})
    assert len(client.get("/api/executions").json()) == 3


# -- store level ---------------------------------------------------------------------------


def _record(store: SqliteStore):
    lab = build_support_lab(store)
    return lab.record(SCENARIO, "fixed")


def test_owned_executions_expire_after_the_ttl():
    base = SqliteStore(":memory:", owner_ttl_s=3600)
    scoped = base.scoped("alice")
    ex = _record(SqliteStore(":memory:"))
    scoped.save(ex)
    unowned = _record(SqliteStore(":memory:"))
    base.save(unowned)
    assert base.expire() == 0
    removed = base.expire(now=__import__("time").time() + 3601)
    assert removed == 1
    assert scoped.count() == 0
    assert base.get(unowned.id).id == unowned.id  # unowned (local) rows never expire


def test_ownership_conflict_on_reused_id():
    base = SqliteStore(":memory:")
    ex = _record(SqliteStore(":memory:"))
    base.scoped("alice").save(ex)
    base.scoped("alice").save(ex)  # same owner may update its own row
    with pytest.raises(OwnershipConflict):
        base.scoped("bob").save(ex)
    with pytest.raises(OwnershipConflict):
        base.save(ex)  # an unowned write cannot take over an owned row either


def test_existing_database_is_migrated_in_place(tmp_path):
    path = tmp_path / "old.sqlite3"
    ex = _record(SqliteStore(":memory:"))
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE executions (id TEXT PRIMARY KEY, app TEXT NOT NULL,"
            " scenario TEXT NOT NULL, variant TEXT NOT NULL, mode TEXT NOT NULL,"
            " status TEXT NOT NULL, created_at TEXT NOT NULL, schema_version TEXT NOT NULL,"
            " summary_json TEXT NOT NULL, body_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ex.id,
                ex.app,
                ex.scenario,
                ex.variant,
                ex.mode.value,
                ex.status.value,
                ex.created_at,
                ex.schema_version,
                ex.summary().model_dump_json(),
                ex.model_dump_json(),
            ),
        )
    store = SqliteStore(path)
    assert store.get(ex.id) == ex
    assert [s.id for s in store.list()] == [ex.id]
    assert store.scoped("anyone").list() == []
