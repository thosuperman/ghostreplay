"""`support-agent-lab` command line."""

from __future__ import annotations

import sys

from ghostreplay.lab import Lab
from ghostreplay.server.cli import lab_main
from ghostreplay.storage import SqliteStore

from .scenario import DuplicateRefundScenario

APP = "support-agent"
PORT = 8101


def build_lab(store: SqliteStore) -> Lab:
    return Lab(APP, [DuplicateRefundScenario()], store)


def main(argv: list[str] | None = None) -> int:
    return lab_main(
        prog="support-agent-lab", app_name=APP, default_port=PORT, build_lab=build_lab, argv=argv
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
