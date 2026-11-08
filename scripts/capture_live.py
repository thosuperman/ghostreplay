"""Record the genuine live-LLM capture library shipped with the labs.

    set -a; . ./.env; set +a
    GHOSTREPLAY_LIVE=1 uv run python scripts/capture_live.py

Every capture is a real execution: a live model chooses the tools, the tools make real HTTP
requests to the lab services and real SQLite writes. Controlled faults are labelled in the
trace. Nothing is filtered by outcome: whatever the model decided is what gets saved.

Writes ``apps/<lab>/src/<pkg>/captures/<name>.trace.json``; the servers load them as a
shared, read-only library that visitors can inspect, replay offline and re-execute.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from devops_agent.cli import build_lab as build_devops
from ghostreplay.llm import LiveModelConfig
from ghostreplay.models import Execution, FaultSpec, FaultTarget
from ghostreplay.storage import SqliteStore
from support_agent.cli import build_lab as build_support

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(UTC).strftime("%Y-%m-%d")


def save(ex: Execution, directory: Path, name: str, title: str) -> None:
    ex = ex.model_copy(update={"title": f"{title} · genuine live capture, {STAMP}"})
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.trace.json").write_text(ex.model_dump_json(indent=1), encoding="utf-8")
    failed = [i.id for i in ex.invariants if i.status == "failed"]
    print(
        f"  saved {name}: {ex.id} status={ex.status.value} model={ex.provenance.model} failed={failed}"
    )


def injected_terminate(model: str, occurrence: int, instance_ids: list[str]) -> FaultSpec:
    """Controlled fault on a model decision: 'what if the model follows runbook RB-7 v1?'"""
    return FaultSpec(
        id="model-follows-runbook-literally",
        kind="incorrect_output",
        target=FaultTarget(kind="model_call", name=model, occurrence=occurrence),
        params={
            "set": {
                "content": "",
                "stop_reason": "tool_use",
                "provider_content": None,
                "tool_calls": [
                    {
                        "id": "injected_terminate_1",
                        "name": "ec2.terminate_instances",
                        "arguments": {
                            "instance_ids": instance_ids,
                            "reason": "Runbook RB-7: instances report status_check=impaired",
                        },
                    }
                ],
            }
        },
        description=(
            "Controlled fault injection: the model's decision is replaced with terminating the "
            "instances the monitoring view reports as impaired (following runbook v1 literally)."
        ),
    )


def main() -> int:
    live = LiveModelConfig.from_env()
    if live is None:
        print("GHOSTREPLAY_LIVE=1 and a provider key are required", file=sys.stderr)
        return 2

    print("support-agent (live)")
    lab = build_support(SqliteStore(":memory:"))
    lab.live = live
    sc = lab.scenario("duplicate-refund")
    out = ROOT / "apps/support-agent/src/support_agent/captures"
    for variant, name, title in (
        (
            "vulnerable",
            "refund-buggy",
            "Buggy support agent, refund service times out after commit",
        ),
        ("fixed", "refund-fixed", "Fixed support agent, refund service times out after commit"),
    ):
        ex = lab.record(
            sc.id, variant, conditions=sc.incident_conditions(), model="live", title=title
        )
        save(ex, out, name, title)

    print("devops-agent (live)")
    lab = build_devops(SqliteStore(":memory:"))
    lab.live = live
    sc = lab.scenario("unsafe-infra-action")
    out = ROOT / "apps/devops-agent/src/devops_agent/captures"
    natural: dict[str, Execution] = {}
    for variant, name, title in (
        ("vulnerable", "devops-v1", "Runbook v1 workflow, stale monitoring"),
        ("fixed", "devops-v2", "Runbook v2 workflow, stale monitoring"),
    ):
        ex = lab.record(
            sc.id, variant, conditions=sc.incident_conditions(), model="live", title=title
        )
        natural[variant] = ex
        save(ex, out, name, title)
    ids = [i["instance_id"] for i in natural["vulnerable"].final_state["instances"]]
    for variant, name, title in (
        (
            "vulnerable",
            "devops-v1-injected",
            "Runbook v1 workflow, model decision injected (terminate)",
        ),
        ("fixed", "devops-v2-injected", "Runbook v2 workflow, model decision injected (terminate)"),
    ):
        ref = natural[variant]
        model = ref.provenance.model
        cf = lab.counterfactual(
            ref.id, [injected_terminate(model, 2, ids)], mode="branch", title=title
        )
        save(cf, out, name, title)
        # A counterfactual references its source; ship the source in the library too.

    manifest = {"captured": STAMP, "model": live.model, "provider": live.provider}
    for d in (
        "apps/support-agent/src/support_agent/captures",
        "apps/devops-agent/src/devops_agent/captures",
    ):
        (ROOT / d / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
