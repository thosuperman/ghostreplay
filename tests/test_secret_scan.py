"""Tests for scripts/secret_scan.py (the scanner behind the secret-scan Kiro hook)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "secret_scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("secret_scan", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["secret_scan"] = module
    spec.loader.exec_module(module)
    return module


secret_scan = _load()

# Fake secrets are assembled at runtime so this file never contains one literally.
PLANTED = {
    "aws_access_key_id": "AKIA" + "Q" * 16,
    "api_key": "sk-" + "a1b2c3d4" * 3,
    "stripe_live_key": "sk_" + "live_" + "Z" * 24,
    "github_token": "ghp" + "_" + "x" * 36,
    "private_key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "bearer_token": "Authorization: " + "Bearer " + "t" * 32,
}


@pytest.mark.parametrize(("kind", "value"), sorted(PLANTED.items()))
def test_detects_planted_secret(tmp_path, kind, value):
    path = tmp_path / "config.py"
    path.write_text(f"ok = 1\nvalue = {value!r}\n", encoding="utf-8")
    findings = secret_scan.scan([path], tmp_path)
    assert [(f.path, f.line, f.kind) for f in findings] == [("config.py", 2, kind)]


def test_reports_path_line_kind_and_exits_nonzero(tmp_path, capsys, monkeypatch):
    path = tmp_path / "leak.md"
    path.write_text("# notes\n\nkey: " + PLANTED["aws_access_key_id"] + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert secret_scan.main(["leak.md"]) == 1
    assert capsys.readouterr().out.strip() == "leak.md:3: aws_access_key_id"


def test_allow_marker_skips_intentional_fixture_lines(tmp_path):
    path = tmp_path / "test_fixture.py"
    marker = "# " + secret_scan.ALLOW_MARKER
    path.write_text(
        f"fake = {PLANTED['api_key']!r}  {marker}\nreal = {PLANTED['api_key']!r}\n",
        encoding="utf-8",
    )
    findings = secret_scan.scan([path], tmp_path)
    assert [f.line for f in findings] == [2]


def test_benign_lookalikes_are_not_flagged(tmp_path):
    path = tmp_path / "benign.py"
    path.write_text(
        "\n".join(
            [
                "idempotency_key = 'refund:TCK-5521:pay_3KQ81:12900'",
                "header = 'Bearer short'",
                "name = 'task-runner'",
                "AKIA_PREFIX = 'AKIA'",
            ]
        ),
        encoding="utf-8",
    )
    assert secret_scan.scan([path], tmp_path) == []


def test_lock_and_binary_files_are_skipped(tmp_path):
    secret = PLANTED["github_token"]
    (tmp_path / "uv.lock").write_text(secret, encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text(secret, encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01" + secret.encode())
    (tmp_path / "logo.png").write_bytes(secret.encode())
    assert secret_scan.scan([tmp_path], tmp_path) == []


def test_current_repository_is_clean(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert secret_scan.main([]) == 0, capsys.readouterr().out
