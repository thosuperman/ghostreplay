"""`devops-agent-lab` command line."""

from __future__ import annotations

import sys
from pathlib import Path

from ghostreplay.lab import Lab
from ghostreplay.server.cli import lab_main
from ghostreplay.storage import SqliteStore

from .scenario import UnsafeInfraActionScenario

APP = "devops-agent"
PORT = 8102


#: Genuine live-model captures shipped with this lab (see scripts/capture_live.py).
CAPTURES_DIR = Path(__file__).with_name("captures")


def build_lab(store: SqliteStore) -> Lab:
    lab = Lab(APP, [UnsafeInfraActionScenario()], store)
    lab.library_dir = CAPTURES_DIR
    return lab


def main(argv: list[str] | None = None) -> int:
    return lab_main(
        prog="devops-agent-lab", app_name=APP, default_port=PORT, build_lab=build_lab, argv=argv
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
