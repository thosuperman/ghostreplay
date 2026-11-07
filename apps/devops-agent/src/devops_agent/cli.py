"""`devops-agent-lab` command line."""

from __future__ import annotations

import sys

from ghostreplay.lab import Lab
from ghostreplay.server.cli import lab_main
from ghostreplay.storage import SqliteStore

from .scenario import UnsafeInfraActionScenario

APP = "devops-agent"
PORT = 8102


def build_lab(store: SqliteStore) -> Lab:
    return Lab(APP, [UnsafeInfraActionScenario()], store)


def main(argv: list[str] | None = None) -> int:
    return lab_main(
        prog="devops-agent-lab", app_name=APP, default_port=PORT, build_lab=build_lab, argv=argv
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
