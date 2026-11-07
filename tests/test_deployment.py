"""Deployment surface: gateway, health checks and the public hardening profile."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ghostreplay.server.app import create_app
from ghostreplay.server.gateway import create_gateway, discover_labs
from ghostreplay.server.settings import RateLimiter, ServerSettings
from ghostreplay.storage import SqliteStore
from support_agent.cli import build_lab as build_support_lab

PUBLIC = ServerSettings.from_env({"GHOSTREPLAY_PUBLIC": "1", "GHOSTREPLAY_LIVE": "1"})


def test_both_labs_are_discoverable_as_independent_apps():
    assert {"support", "devops"} <= set(discover_labs())


def test_gateway_serves_both_labs_health_and_dashboard(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>GhostReplay Lab</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    client = TestClient(create_gateway(db_dir=":memory:", dashboard_dir=dist))

    assert client.get("/healthz").json()["labs"] == ["devops", "support"]
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and set(health["labs"]) == {"support", "devops"}
    assert client.get("/lab/support/api/info").json()["app"] == "support-agent"
    assert client.get("/lab/devops/api/info").json()["app"] == "devops-agent"
    assert client.get("/lab/support/api/health").json()["status"] == "ok"
    # SPA routes fall back to index.html; assets are served with long caching.
    assert "GhostReplay Lab" in client.get("/executions/123").text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    # Path traversal cannot escape the dashboard directory.
    assert "GhostReplay Lab" in client.get("/..%2F..%2Fetc%2Fpasswd").text


def test_gateway_runs_the_full_demo_through_the_mounted_api():
    client = TestClient(create_gateway(db_dir=":memory:"))
    for lab, scenario in (("support", "duplicate-refund"), ("devops", "unsafe-infra-action")):
        story = client.post(f"/lab/{lab}/api/demo/prepare", json={"scenario": scenario}).json()
        assert story["ok"] is True, story
        listed = client.get(f"/lab/{lab}/api/executions").json()
        assert len(listed) >= 5


def test_public_profile_disables_live_mode_and_clearing():
    lab = build_support_lab(SqliteStore(":memory:"))
    client = TestClient(create_app(lab, settings=PUBLIC))
    info = client.get("/api/info").json()
    assert info["public"] is True and info["live_model"] is None and info["can_clear"] is False
    assert info["storage"] == "sqlite"  # no server paths leaked
    assert client.delete("/api/executions").status_code == 403
    r = client.post(
        "/api/runs/record",
        json={"scenario": "duplicate-refund", "variant": "fixed", "model": "live"},
    )
    assert r.status_code == 400 and "live AI mode is not enabled" in r.json()["detail"]


def test_public_profile_rate_limits_and_caps_bodies():
    settings = ServerSettings(public=True, rate_limit_per_minute=3, max_body_bytes=200)
    client = TestClient(create_app(build_support_lab(SqliteStore(":memory:")), settings=settings))
    body = {"scenario": "duplicate-refund", "variant": "fixed"}
    codes = [client.post("/api/runs/record", json=body).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    big = client.post(
        "/api/runs/record", content=b"x" * 500, headers={"content-type": "application/json"}
    )
    assert big.status_code == 413
    assert client.get("/api/executions").status_code == 200  # reads are not limited


def test_public_store_keeps_a_bounded_number_of_executions():
    settings = ServerSettings(public=True, max_executions=3)
    lab = build_support_lab(SqliteStore(":memory:"))
    client = TestClient(create_app(lab, settings=settings))
    for _ in range(5):
        client.post("/api/runs/record", json={"scenario": "duplicate-refund", "variant": "fixed"})
    assert len(client.get("/api/executions").json()) == 3


def test_rate_limiter_window_slides():
    rl = RateLimiter(2, window_s=10)
    assert rl.allow("a", now=0)[0] and rl.allow("a", now=1)[0]
    allowed, retry = rl.allow("a", now=2)
    assert not allowed and 0 < retry <= 10
    assert rl.allow("b", now=2)[0]  # per-client
    assert rl.allow("a", now=10.5)[0]


def test_local_profile_is_unrestricted_by_default():
    s = ServerSettings.from_env({})
    assert not s.public and s.allow_clear and s.rate_limit_per_minute == 0
    assert "http://127.0.0.1:5173" in s.allow_origins
