import { useMemo, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import { Inspector, InvariantList, Timeline } from "../components/execution";
import { ExecTypeBadges } from "../components/ExecTypeBadges";
import { Badge, Button, Card, ErrorBox, JsonView, Loading, ModeBadge, SectionHeader, Stat, StatusBadge } from "../components/ui";
import { ms } from "../lib/format";
import { href } from "../lib/router";
import { useAsync } from "../lib/useAsync";

export function ExecutionView({ lab, id, focus }: { lab: LabId; id: string; focus?: string }) {
  const { data: ex, error, loading } = useAsync(() => api.execution(lab, id), [lab, id]);
  const [selected, setSelected] = useState<string | undefined>(focus);

  const selectedEvent = useMemo(() => {
    if (!ex) return undefined;
    const sel = selected ?? ex.events.find((e) => e.fault || e.kind === "divergence" || (e.destructive && !e.error))?.event_id ?? ex.events.find((e) => e.kind === "tool_call")?.event_id;
    return ex.events.find((e) => e.event_id === sel);
  }, [ex, selected]);

  if (error) return <ErrorBox error={error} />;
  if (loading || !ex) return <Loading label="Loading execution…" />;

  const s = ex.summary;
  const failed = ex.invariants.filter((i) => i.status === "failed").length;
  return (
    <div className="animate-fade">
      <SectionHeader
        eyebrow={`${LABS[lab].name} · ${ex.scenario}`}
        title={<span className="flex flex-wrap items-center gap-3">{ex.title || "Execution"} <ModeBadge mode={ex.mode} /> <StatusBadge status={ex.status} /> <ExecTypeBadges e={ex} /></span>}
        actions={
          <>
            {ex.mode === "record" && <Button variant="primary" href={href({ name: "replay", lab, id: ex.id })}>▶ Replay offline</Button>}
            <Button href={href({ name: "failure-lab", lab, id: ex.reference_execution_id && ex.mode !== "record" ? ex.reference_execution_id : ex.id })}>⚡ Failure Lab</Button>
            {ex.reference_execution_id && <Button href={href({ name: "diff", lab, a: ex.reference_execution_id, b: ex.id })}>Diff vs reference</Button>}
            <Button href={href({ name: "regression", lab, id: ex.id })}>Regression</Button>
          </>
        }
      >
        <span className="font-mono text-xs text-ink-400">{ex.id}</span>
        {ex.reference_execution_id && (
          <span className="ml-3 text-xs">
            reference <a className="font-mono text-violet-300 hover:underline" href={href({ name: "execution", lab, id: ex.reference_execution_id })}>{ex.reference_execution_id}</a>
          </span>
        )}
      </SectionHeader>

      <div className="mb-5 grid grid-cols-2 gap-4 rounded-xl border hairline bg-ink-900/80 p-4 md:grid-cols-4 xl:grid-cols-8">
        <Stat label="Agent" value={<span className="text-sm">{ex.agent}</span>} />
        <Stat label="Outcome" value={ex.output?.status ?? "—"} tone={ex.output?.status === "success" ? undefined : "amber"} />
        <Stat label="Invariants" value={`${ex.invariants.length - failed}/${ex.invariants.length}`} tone={failed ? "red" : "green"} />
        <Stat label="Tool calls" value={s.tool_calls} />
        <Stat label="Model calls" value={s.model_calls} />
        <Stat label="Errors" value={s.errors} tone={s.errors ? "amber" : undefined} />
        <Stat label="Destructive" value={s.destructive_calls} tone={s.destructive_calls ? "red" : undefined} />
        <Stat label="Simulated time" value={ms(ex.duration_ms)} />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="amber" title="Where decisions came from">{ex.provenance.label}</Badge>
        <Badge tone="cyan">tools: {ex.provenance.tool_backends}</Badge>
        {Object.entries(ex.conditions).map(([k, v]) => <Badge key={k}>{k}={v}</Badge>)}
        {ex.faults.map((f) => <Badge key={f.id} tone="fuchsia">⚡ {f.kind} → {f.target.name}#{f.target.occurrence ?? "*"}</Badge>)}
      </div>

      {ex.divergence && (
        <div className="mb-5 rounded-xl border border-amber-400/25 bg-amber-400/[0.05] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="amber">divergence · {ex.divergence.type}</Badge>
            {ex.divergence.after_fault && <Badge tone="fuchsia">after injected fault</Badge>}
            <span className="text-[13px] text-amber-100">{ex.divergence.message}</span>
          </div>
          {ex.divergence.changes.length > 0 && (
            <div className="mt-2 space-y-0.5 font-mono text-[11px] text-ink-300">
              {ex.divergence.changes.slice(0, 5).map((c) => (
                <div key={c.path}>
                  <span className="text-amber-300">{c.path}</span>: {JSON.stringify(c.before)?.slice(0, 60)} → {JSON.stringify(c.after)?.slice(0, 60)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {ex.notes.map((n) => (
        <div key={n} className="mb-3 rounded-lg border border-violet-400/20 bg-violet-500/[0.05] px-4 py-2 text-[12.5px] text-violet-100">{n}</div>
      ))}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card title="Execution timeline" subtitle="Chronological events · click to inspect · bars show simulated time">
          <Timeline execution={ex} selected={selectedEvent?.event_id} onSelect={(e) => setSelected(e.event_id)} highlight={ex.invariants.filter((i) => i.status === "failed").flatMap((i) => i.evidence)} />
        </Card>
        <div className="space-y-5 xl:sticky xl:top-20 xl:self-start">
          <Card title="Inspector">
            <Inspector key={selectedEvent?.event_id} event={selectedEvent} />
          </Card>
          <Card title="Safety invariants" subtitle={`${failed} failed of ${ex.invariants.length}`}>
            <InvariantList invariants={ex.invariants} onEvidence={(id) => setSelected(id)} />
          </Card>
          {ex.output && (
            <Card title="Agent output" subtitle={`status: ${ex.output.status}`}>
              <div className="p-4 text-[13px] leading-relaxed text-ink-100">“{ex.output.message}”</div>
            </Card>
          )}
          {ex.final_state && (
            <Card title="Final observable state">
              <div className="p-3"><JsonView value={ex.final_state} maxHeight="20rem" /></div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
