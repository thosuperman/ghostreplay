"""`ghostreplay` command line.

  ghostreplay inspect TRACE            summarise a trace file (validated, never executed)
  ghostreplay diff A B                 structural diff of two trace files
  ghostreplay replay TRACE --app M:V   strict offline replay with *your* agent code
  ghostreplay export ID --store DIR --app NAME --out DIR   write a stored run as a trace file
  ghostreplay test CASES --import M    run regression cases (exit 1 on unexpected outcome)
  ghostreplay scenarios                list registered scenarios
  ghostreplay serve                    serve the bundled labs and dashboard

A trace file is data. Replaying it always needs the agent code that produced it: pass the
module that creates your ``GhostReplay`` object with ``--app``. Nothing in a trace can name
code to run.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from .core.errors import GhostReplayError, ScenarioNotFound
from .lab.registry import available
from .models import EventKind, Execution
from .regression import load_case, reports_to_json, reports_to_junit, run_case
from .storage.files import MAX_TRACE_BYTES
from .storage.parsing import parse_document


def _load_trace(path: Path) -> Execution:
    if not path.is_file():
        raise SystemExit(f"error: {path} is not a file")
    if path.stat().st_size > MAX_TRACE_BYTES:
        raise SystemExit(f"error: {path} is larger than {MAX_TRACE_BYTES} bytes")
    try:
        return parse_document(Execution, path.read_bytes(), source=f"trace file {path.name}")
    except GhostReplayError as exc:
        raise SystemExit(f"error: {exc}") from None


def _import_modules(names: list[str]) -> None:
    for name in names:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            raise SystemExit(f"error: cannot import {name!r}: {exc}") from None


def _load_app(spec: str) -> Any:
    from .sdk import GhostReplay

    module_name, _, attr = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(f"error: cannot import {module_name!r}: {exc}") from None
    if attr:
        ghost = getattr(module, attr, None)
    else:
        found = [v for v in vars(module).values() if isinstance(v, GhostReplay)]
        ghost = found[0] if len(found) == 1 else None
    if not isinstance(ghost, GhostReplay):
        raise SystemExit(
            f"error: {spec!r} does not name a GhostReplay object (use module:attribute)"
        )
    return ghost


def _summary(ex: Execution) -> dict[str, Any]:
    tool_calls = [e for e in ex.events if e.kind == EventKind.TOOL_CALL]
    model_calls = [e for e in ex.events if e.kind == EventKind.MODEL_CALL]
    return {
        "id": ex.id,
        "app": ex.app,
        "scenario": ex.scenario,
        "agent": ex.variant,
        "mode": ex.mode.value,
        "status": ex.status.value,
        "schema_version": ex.schema_version,
        "model": ex.provenance.label,
        "events": len(ex.events),
        "model_calls": len(model_calls),
        "tool_calls": len(tool_calls),
        "tool_errors": sum(1 for e in tool_calls if e.error),
        "faults": [f"{f.kind}@{f.target.name}" for f in ex.faults],
        "invariants": {i.id: i.status for i in ex.invariants},
        "output": ex.output.model_dump(mode="json") if ex.output else None,
        "divergence": ex.divergence.message if ex.divergence else None,
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    ex = _load_trace(args.trace)
    info = _summary(ex)
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(
        f"{ex.id}  app={ex.app}  agent={ex.variant}  mode={ex.mode.value}  status={ex.status.value}"
    )
    print(f"model: {info['model']}")
    if info["faults"]:
        print(f"faults: {', '.join(info['faults'])}")
    print(f"\n{'seq':>4}  {'kind':<15} {'name':<32} {'source':<10} result")
    for e in ex.events:
        if e.kind not in (
            EventKind.TOOL_CALL,
            EventKind.MODEL_CALL,
            EventKind.AGENT_STEP,
            EventKind.GUARD,
        ):
            continue
        result = (
            f"error {e.error.type}" if e.error else ("fault " + e.fault.kind if e.fault else "ok")
        )
        print(f"{e.seq:>4}  {e.kind.value:<15} {e.name[:32]:<32} {e.source.value:<10} {result}")
    if ex.output:
        print(f"\noutput ({ex.output.status}): {ex.output.message}")
    for inv in ex.invariants:
        print(f"  [{inv.status.upper():12}] {inv.id}: {inv.message}")
    if ex.divergence:
        print(f"divergence: {ex.divergence.message}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    from .diff import diff_executions

    d = diff_executions(_load_trace(args.a), _load_trace(args.b))
    if args.json:
        print(d.model_dump_json(indent=2))
    else:
        print("identical" if d.identical else "different")
        if d.first_divergence:
            print(f"first divergence: {d.first_divergence.get('summary')}")
        for entry in d.entries:
            print(f"  [{entry.type}] {entry.summary}")
        b = d.behavior
        print(
            f"status: {b.status[0]} -> {b.status[1]}   output: {b.output_status[0]} -> {b.output_status[1]}"
        )
        for inv in b.invariants:
            print(f"  invariant {inv.get('id')}: {inv.get('a')} -> {inv.get('b')}")
    return 1 if (args.fail_on_diff and not d.identical) else 0


def cmd_replay(args: argparse.Namespace) -> int:
    ghost = _load_app(args.app)
    try:
        original = ghost.load(args.trace)
    except GhostReplayError as exc:
        raise SystemExit(f"error: {exc}") from None
    run = ghost.replay(original)
    d = ghost.diff(original, run)
    if args.json:
        print(
            json.dumps(
                {
                    **_summary(run.execution),
                    "identical": d.identical,
                    "live_calls": run.live_calls,
                    "replayed_calls": run.replayed_calls,
                },
                indent=2,
            )
        )
    else:
        print(run.explain())
        print(
            f"live calls: {run.live_calls}   served from recording: {run.replayed_calls}   "
            f"identical to the original: {d.identical}"
        )
    return 0 if run.status == "completed" and d.identical else 1


def cmd_export(args: argparse.Namespace) -> int:
    from .storage import SqliteStore, export_execution

    db = Path(args.store) / f"{args.app}.sqlite3"
    if not db.is_file():
        raise SystemExit(f"error: no store at {db}")
    store = SqliteStore(db)
    try:
        ex = store.get(args.id)
    except GhostReplayError as exc:
        raise SystemExit(f"error: {exc}") from None
    print(export_execution(ex, args.out))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    _import_modules(args.imports)
    files: list[Path] = []
    for p in args.cases:
        files.extend(sorted(p.glob("*.case.json")) if p.is_dir() else [p])
    if not files:
        raise SystemExit("error: no *.case.json files found")
    reports = []
    for f in files:
        try:
            report = run_case(load_case(f))
        except ScenarioNotFound as exc:
            raise SystemExit(
                f"error: {exc}\nhint: pass --import with the module that creates your "
                "GhostReplay app, e.g. --import my_agent.agent"
            ) from None
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ghostreplay",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect", help="summarise a trace file")
    i.add_argument("trace", type=Path)
    i.add_argument("--json", action="store_true", help="machine-readable output")

    d = sub.add_parser("diff", help="structural diff of two trace files")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    d.add_argument("--json", action="store_true")
    d.add_argument("--fail-on-diff", action="store_true", help="exit 1 when they differ")

    r = sub.add_parser("replay", help="strict offline replay of a trace with your agent code")
    r.add_argument("trace", type=Path)
    r.add_argument("--app", required=True, help="module[:attribute] of your GhostReplay object")
    r.add_argument("--json", action="store_true")

    e = sub.add_parser("export", help="write a stored run as a trace file")
    e.add_argument("id")
    e.add_argument("--store", required=True, help="the storage directory passed to GhostReplay")
    e.add_argument("--app", required=True, help="the app name passed to GhostReplay")
    e.add_argument("--out", type=Path, default=Path("."))

    t = sub.add_parser("test", help="run regression case files")
    t.add_argument("cases", nargs="+", type=Path, help="*.case.json files or directories")
    t.add_argument(
        "--import",
        dest="imports",
        action="append",
        default=[],
        help="module that registers your GhostReplay app (repeatable)",
    )
    t.add_argument("--json", type=Path, help="write a JSON report")
    t.add_argument("--junit", type=Path, help="write a JUnit XML report")

    sub.add_parser("scenarios", help="list registered scenarios")

    g = sub.add_parser("serve", help="serve the bundled labs and dashboard on one port")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8100)
    g.add_argument("--db", default=os.environ.get("GHOSTREPLAY_DB_DIR", ".ghostreplay"))
    g.add_argument(
        "--dashboard",
        type=Path,
        default=Path(os.environ.get("GHOSTREPLAY_DASHBOARD_DIR", "apps/dashboard/dist")),
        help="built dashboard directory (served at /)",
    )
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        try:
            import uvicorn

            from .server.gateway import create_gateway
        except ImportError:
            raise SystemExit(
                "error: `serve` needs the server extra: pip install 'ghostreplay[server]'"
            ) from None
        app = create_gateway(db_dir=args.db, dashboard_dir=args.dashboard)
        print(f"ghostreplay: labs and dashboard on http://{args.host}:{args.port}/")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning", proxy_headers=True)
        return 0
    if args.cmd == "scenarios":
        for sid, sc in sorted(available().items()):
            print(f"{sid:28} {sc.app:16} {sc.title}")
        return 0
    handlers = {
        "inspect": cmd_inspect,
        "diff": cmd_diff,
        "replay": cmd_replay,
        "export": cmd_export,
        "test": cmd_test,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
