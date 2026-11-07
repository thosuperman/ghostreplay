"""Dependency-free secret scanner for the repository.

Usage::

    uv run python scripts/secret_scan.py            # scan every tracked or unignored file
    uv run python scripts/secret_scan.py a.py b.md  # scan only these paths

Flags AWS access key ids, ``sk-`` / ``sk_live_`` style API keys, GitHub tokens, private key
headers and bearer tokens with long values. A line that intentionally contains a fake secret
(a test fixture) is skipped when it carries the marker ``secret-scan: allow``.

Binary files, lock files and files that no longer exist are skipped. Exit status is 1 when
anything is found (one ``path:line: kind`` line per finding), 0 otherwise.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ALLOW_MARKER = "secret-scan: allow"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("api_key", re.compile(r"\bsk-(?:live-|proj-|ant-)?[A-Za-z0-9_\-]{16,}")),
    ("stripe_live_key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("github_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{20,}")),
)

LOCK_FILES = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "Cargo.lock",
    }
)
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".sqlite3",
        ".db",
        ".pyc",
    }
)
SKIP_DIRS = frozenset(
    {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
)
MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def is_skipped(path: Path) -> bool:
    """Lock files and known binary formats are never scanned."""
    name = path.name
    return name in LOCK_FILES or name.endswith(".lock") or path.suffix.lower() in BINARY_SUFFIXES


def _read_text(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:  # binary content
        return None
    return data.decode("utf-8", errors="replace")


def scan_text(text: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        seen: set[str] = set()
        for kind, pattern in PATTERNS:
            if kind not in seen and pattern.search(line):
                seen.add(kind)
                findings.append(Finding(path, lineno, kind))
    return findings


def scan_file(path: Path, display: str | None = None) -> list[Finding]:
    if is_skipped(path):
        return []
    text = _read_text(path)
    if text is None:
        return []
    return scan_text(text, display or str(path))


def _walk(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def repository_files(root: Path) -> list[Path]:
    """Tracked plus untracked-but-not-ignored files; falls back to a directory walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted(_walk(root))
    names = sorted({n for n in out.decode("utf-8", errors="replace").split("\0") if n})
    return [root / n for n in names]


def scan(paths: Iterable[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        targets = _walk(path) if path.is_dir() else [path]
        for target in targets:
            try:
                display = str(target.resolve().relative_to(root.resolve()))
            except ValueError:
                display = str(target)
            findings.extend(scan_file(target, display))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path.cwd()
    paths = [Path(a) for a in args] if args else repository_files(root)
    findings = scan(paths, root)
    for finding in findings:
        print(finding)
    if findings:
        print(
            f"secret-scan: {len(findings)} finding(s). Remove the secret, or mark an "
            f"intentional test fixture line with '{ALLOW_MARKER}'.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
