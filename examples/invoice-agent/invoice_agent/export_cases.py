"""Record the timeout-after-commit incident and write regression tests for both agents.

python -m invoice_agent.export_cases tests/regression
"""

from __future__ import annotations

import sys
from pathlib import Path

from ghostreplay import fault

from .agent import ghost


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0] if args else "tests/regression")
    incident = ghost.record(
        agent="buggy", faults=[fault("timeout_after_commit", "payments.pay")], title="incident"
    )
    for agent in ("buggy", "fixed"):
        case_path, test_path = ghost.write_regression_test(
            incident, out, agent=agent, import_module="invoice_agent.agent"
        )
        print(f"wrote {case_path} and {test_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
