"""`ghostreplay` command line: list scenarios and run regression cases with reports."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .lab.registry import available
from .regression import load_case, reports_to_json, reports_to_junit, run_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ghostreplay", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scenarios", help="list registered scenarios")
    g = sub.add_parser("serve", help="serve every installed lab and the dashboard on one port")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8100)
    g.add_argument("--db", default=os.environ.get("GHOSTREPLAY_DB_DIR", ".ghostreplay"))
    g.add_argument(
        "--dashboard",
        type=Path,
        default=Path(os.environ.get("GHOSTREPLAY_DASHBOARD_DIR", "apps/dashboard/dist")),
        help="built dashboard directory (served at /) ",
    )
    t = sub.add_parser("test", help="run regression case files")
    t.add_argument("cases", nargs="+", type=Path, help="*.case.json files or directories")
    t.add_argument("--json", type=Path, help="write a JSON report")
    t.add_argument("--junit", type=Path, help="write a JUnit XML report")
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .server.gateway import create_gateway

        app = create_gateway(db_dir=args.db, dashboard_dir=args.dashboard)
        print(f"ghostreplay: labs and dashboard on http://{args.host}:{args.port}/")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning", proxy_headers=True)
        return 0

    if args.cmd == "scenarios":
        for sid, sc in sorted(available().items()):
            print(f"{sid:28} {sc.app:16} {sc.title}")
        return 0

    files: list[Path] = []
    for p in args.cases:
        files.extend(sorted(p.glob("*.case.json")) if p.is_dir() else [p])
    reports = []
    for f in files:
        report = run_case(load_case(f))
        reports.append(report)
        ok = "ok " if report.outcome_matches_expectation else "BAD"
        print(f"[{ok}] {report.explain()}\n")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(reports_to_json(reports), encoding="utf-8")
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        args.junit.write_text(reports_to_junit(reports), encoding="utf-8")
    bad = sum(1 for r in reports if not r.outcome_matches_expectation)
    print(f"{len(reports) - bad}/{len(reports)} cases matched expectations")
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
