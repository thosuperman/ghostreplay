"""Every runnable Python block in docs/sdk and the example files run exactly as published.

A block whose first line is ``# fragment`` is an excerpt and is not executed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "sdk"
BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def _blocks() -> list[tuple[str, str]]:
    out = []
    for md in sorted(DOCS.glob("*.md")):
        for i, code in enumerate(BLOCK.findall(md.read_text(encoding="utf-8"))):
            if code.lstrip().startswith("# fragment"):
                continue
            out.append((f"{md.name}#{i + 1}", code))
    return out


def _run(code_or_file: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    args = (
        [sys.executable, str(code_or_file)]
        if isinstance(code_or_file, Path)
        else [sys.executable, "-c", code_or_file]
    )
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)


def test_docs_have_runnable_blocks():
    assert len(_blocks()) >= 12
    expected = {
        "quickstart",
        "installation",
        "python-api",
        "instrumentation",
        "model-adapters",
        "tool-wrapping",
        "recording",
        "replay",
        "failure-injection",
        "regression-testing",
        "trace-import-export",
        "ci-integration",
        "limitations",
    }
    assert {p.stem for p in DOCS.glob("*.md")} >= expected


@pytest.mark.parametrize(("name", "code"), _blocks(), ids=[n for n, _ in _blocks()])
def test_doc_block_runs(name: str, code: str, tmp_path: Path):
    proc = _run(code, tmp_path)
    assert proc.returncode == 0, f"{name} failed:\n{proc.stdout}\n{proc.stderr}"


def test_published_examples_run_and_their_generated_test_passes(tmp_path: Path):
    for name in ("hello.py", "quickstart.py"):
        shutil.copy(DOCS / "examples" / name, tmp_path / name)
    hello = _run(tmp_path / "hello.py", tmp_path)
    assert hello.returncode == 0 and hello.stdout.strip() == "completed 0 True", hello.stderr
    qs = _run(tmp_path / "quickstart.py", tmp_path)
    assert qs.returncode == 0, qs.stderr
    assert "[FAIL] charges.at_most_once: customer charged 2 times" in qs.stdout
    assert "replay: completed, live calls 0" in qs.stdout
    assert "buggy: FAIL (expected FAIL)" in qs.stdout and "fixed: PASS (expected PASS)" in qs.stdout
    generated = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/regression"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr


def test_readme_sdk_snippet_is_the_tested_hello_example():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hello = (DOCS / "examples" / "hello.py").read_text(encoding="utf-8").strip()
    assert hello in readme, "README's SDK snippet drifted from docs/sdk/examples/hello.py"
