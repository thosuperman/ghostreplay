"""Shared command line for lab applications (`serve`, `run`, `demo`, `export-cases`)."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from ..lab import Lab
from ..llm import LiveModelConfig
from ..regression import write_case
from ..storage import SqliteStore
from .settings import ServerSettings


def lab_main(
    *,
    prog: str,
    app_name: str,
    default_port: int,
    build_lab: Callable[[SqliteStore], Lab],
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument(
        "--db",
        default=os.environ.get("GHOSTREPLAY_DB_DIR", ".ghostreplay"),
        help="directory for the SQLite store (default: ./.ghostreplay)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="start the lab API (and the built dashboard if present)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=default_port)
    r = sub.add_parser("run", help="record one run and print its verdict")
    r.add_argument("--variant", default=None)
    r.add_argument("--incident", action="store_true", help="use the incident conditions")
    r.add_argument(
        "--live",
        action="store_true",
        help="drive the agent with the live LLM (needs GHOSTREPLAY_LIVE=1 and credentials)",
    )
    sub.add_parser("demo", help="run the full story (incident → replay → fault → fix → proof)")
    e = sub.add_parser("export-cases", help="write regression cases for the headline fault")
    e.add_argument("--out", type=Path, default=Path("tests/regression"))
    args = parser.parse_args(argv)

    settings = ServerSettings.from_env()
    store = SqliteStore(
        Path(args.db) / f"{app_name}.sqlite3", max_executions=settings.max_executions
    )
    lab = build_lab(store)
    lab.live = LiveModelConfig.from_env() if settings.allow_live else None
    scenario = next(iter(lab.scenarios.values()))

    if args.cmd == "serve":
        import uvicorn

        from .app import create_app

        app = create_app(lab, settings=settings)
        print(f"{prog}: API on http://{args.host}:{args.port}/api  (store: {store.path})")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return 0

    if args.cmd == "run":
        variant = args.variant or scenario.vulnerable_variant()
        conditions = scenario.incident_conditions() if args.incident else None
        model = "live" if args.live else "scripted"
        ex = lab.record(
            scenario.id,
            variant,
            conditions=conditions,
            title=f"CLI run ({variant}, {model} model)",
            model=model,
        )
        print(f"model: {ex.provenance.label}")
        print(f"{ex.id}  {ex.status.value}  output={ex.output.status if ex.output else None}")
        for inv in ex.invariants:
            print(f"  [{inv.status.upper():12}] {inv.id}: {inv.message}")
        return 1 if any(i.status == "failed" for i in ex.invariants) else 0

    if args.cmd == "demo":
        story = lab.prepare_demo(scenario.id)
        print(f"\n{story.title}\n" + "=" * len(story.title))
        for step in story.steps:
            flag = "" if step.as_expected else f"  <-- expected {str(step.expected).upper()}"
            print(f"\n{step.title}  [{step.verdict.upper()}]{flag}\n  {step.narrative}")
            print(f"  executions: {', '.join(step.execution_ids)}")
        print()
        for rep in story.reports:
            print(rep.explain())
        if not story.ok:
            print("\nDEMO CHECK FAILED: at least one step did not produce its expected outcome.")
            return 1
        print("\nDemo check passed: every step produced its expected outcome.")
        return 0

    if args.cmd == "export-cases":
        base = lab.record(scenario.id, scenario.vulnerable_variant(), title="Baseline for export")
        preset = next(p for p in scenario.fault_presets() if p.headline)
        cf = lab.counterfactual(base.id, preset.faults, variant=scenario.vulnerable_variant())
        for variant in (scenario.vulnerable_variant(), scenario.fixed_variant()):
            case = lab.case_from_execution(cf.id, variant=variant)
            case_path, test_path = write_case(case, args.out)
            print(f"wrote {case_path} and {test_path}")
        return 0
    return 2
