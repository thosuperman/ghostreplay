import { useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { ExecutionMode, ModelChoice } from "../api/types";
import { verdictOf } from "../components/execution";
import { Badge, Button, Card, cx, Empty, ErrorBox, Loading, ModeBadge, SectionHeader, Select, StatusBadge, Verdict } from "../components/ui";
import { ago, ms } from "../lib/format";
import { href, navigate } from "../lib/router";
import { useAsync } from "../lib/useAsync";

export function Explorer({ lab }: { lab: LabId }) {
  const list = useAsync(() => api.executions(lab), [lab]);
  const scenarios = useAsync(() => api.scenarios(lab), [lab]);
  const info = useAsync(() => api.info(lab), [lab]);
  const [model, setModel] = useState<ModelChoice>("scripted");
  const live = info.data?.live_model ?? null;
  const [mode, setMode] = useState<"all" | ExecutionMode>("all");
  const [busy, setBusy] = useState(false);
  const [variant, setVariant] = useState("vulnerable");
  const [incident, setIncident] = useState(true);
  const [err, setErr] = useState<string>();
  const sc = scenarios.data?.[0];

  const record = async () => {
    if (!sc) return;
    setBusy(true);
    setErr(undefined);
    try {
      const conditions = incident ? Object.fromEntries(sc.conditions.map((c) => [c.id, c.incident])) : {};
      const label = `${incident ? "Incident conditions" : "Healthy conditions"} (${variant}${model === "live" ? ", live AI" : ""})`;
      const s = await api.record(lab, sc.id, variant, conditions, label, model);
      navigate({ name: "execution", lab, id: s.id });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rows = (list.data ?? []).filter((r) => mode === "all" || r.mode === mode);
  return (
    <div className="animate-fade">
      <SectionHeader
        eyebrow={LABS[lab].name}
        title="Execution Explorer"
        actions={
          <>
            <Button variant="ghost" onClick={list.reload}>↻ Refresh</Button>
            {info.data?.can_clear !== false && (
              <Button
                variant="danger"
                onClick={async () => {
                  if (window.confirm("Delete all stored executions for this lab?")) {
                    try {
                      await api.clear(lab);
                      list.reload();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : String(e));
                    }
                  }
                }}
              >
                Clear
              </Button>
            )}
          </>
        }
      >
        {info.data?.isolated_sessions
          ? `Every execution you recorded, replayed or mutated in this browser session, newest first. Runs are private to your session and are deleted after ${info.data.session_ttl_hours ?? 24} hours.`
          : "Every recorded, replayed and counterfactual execution stored by the lab, newest first."}
      </SectionHeader>

      {sc && (
        <Card className="mb-6" title="Record a new run" subtitle="Runs the agent live against a fresh simulated environment and records every interaction.">
          <div className="flex flex-wrap items-end gap-4 p-4">
            <Select label="Agent variant" value={variant} onChange={setVariant} options={sc.variants.map((v) => ({ value: v.id, label: `${v.title} (${v.id})` }))} />
            <Select
              label="Conditions"
              value={incident ? "incident" : "healthy"}
              onChange={(v) => setIncident(v === "incident")}
              options={[
                { value: "incident", label: `Incident: ${sc.conditions.map((c) => `${c.id}=${c.incident}`).join(", ")}` },
                { value: "healthy", label: `Healthy: ${sc.conditions.map((c) => `${c.id}=${c.default}`).join(", ")}` },
              ]}
            />
            {live && (
              <Select
                label="Model"
                value={model}
                onChange={(v) => setModel(v as ModelChoice)}
                options={[
                  { value: "scripted", label: "Scripted (offline, reproducible)" },
                  { value: "live", label: `Live AI: ${live.provider} ${live.model} (≤${live.max_calls} calls)` },
                ]}
              />
            )}
            <Button variant="primary" onClick={() => void record()} disabled={busy}>
              {busy ? "Recording…" : "● Record run"}
            </Button>
            {err && (
              <span role="alert" className="text-sm text-rose-300">
                {err}
              </span>
            )}
          </div>
        </Card>
      )}

      <div className="mb-3 flex flex-wrap gap-1">
        {(["all", "record", "replay", "counterfactual-replay", "branch"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cx("rounded-md px-2.5 py-1 text-xs", mode === m ? "bg-white/10 text-white" : "text-ink-300 hover:text-white")}
          >
            {m === "all" ? `All (${list.data?.length ?? 0})` : m}
          </button>
        ))}
      </div>

      {list.error && <ErrorBox error={list.error} />}
      {list.loading && !list.data && <Loading label="Loading executions…" />}
      {list.data && rows.length === 0 && (
        <Empty title="No executions yet">
          Run the <a className="text-violet-300 underline" href={href({ name: "story", lab })}>guided demo</a> or record a run above.
        </Empty>
      )}
      {rows.length > 0 && (
        <div className="overflow-hidden rounded-xl border hairline bg-ink-900/80">
          <table className="w-full text-[13px]">
            <thead className="border-b hairline bg-white/[0.02] text-[10.5px] uppercase tracking-wider text-ink-400">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Verdict</th>
                <th className="px-4 py-2.5 text-left font-medium">Execution</th>
                <th className="px-4 py-2.5 text-left font-medium">Mode</th>
                <th className="px-4 py-2.5 text-left font-medium">Variant</th>
                <th className="px-4 py-2.5 text-right font-medium">Tools</th>
                <th className="px-4 py-2.5 text-right font-medium">Errors</th>
                <th className="px-4 py-2.5 text-right font-medium">Destructive</th>
                <th className="px-4 py-2.5 text-left font-medium">Failed invariants</th>
                <th className="px-4 py-2.5 text-right font-medium">Sim. time</th>
                <th className="px-4 py-2.5 text-right font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {rows.map((r) => (
                <tr key={r.id} onClick={() => navigate({ name: "execution", lab, id: r.id })} className="cursor-pointer hover:bg-white/[0.03]">
                  <td className="px-4 py-2.5"><Verdict verdict={verdictOf(r)} /></td>
                  <td className="max-w-[22rem] px-4 py-2.5">
                    <div className="truncate text-ink-100">{r.title || "Untitled run"}</div>
                    <div className="font-mono text-[10.5px] text-ink-400">{r.id}{r.injected_faults > 0 && <span className="ml-2 text-fuchsia-300">⚡{r.injected_faults} fault</span>}</div>
                  </td>
                  <td className="px-4 py-2.5"><div className="flex items-center gap-1.5"><ModeBadge mode={r.mode} />{r.status !== "completed" && <StatusBadge status={r.status} />}</div></td>
                  <td className="px-4 py-2.5"><Badge>{r.variant}</Badge></td>
                  <td className="px-4 py-2.5 text-right font-mono text-ink-200">{r.tool_calls}</td>
                  <td className={cx("px-4 py-2.5 text-right font-mono", r.errors ? "text-amber-300" : "text-ink-400")}>{r.errors}</td>
                  <td className={cx("px-4 py-2.5 text-right font-mono", r.destructive_calls ? "text-rose-300" : "text-ink-400")}>{r.destructive_calls}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {r.failed_invariants.slice(0, 2).map((f) => <Badge key={f} tone="red">{f}</Badge>)}
                      {r.failed_invariants.length > 2 && <Badge tone="red">+{r.failed_invariants.length - 2}</Badge>}
                      {r.failed_invariants.length === 0 && <span className="text-xs text-ink-500">—</span>}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-ink-300">{ms(r.duration_ms)}</td>
                  <td className="px-4 py-2.5 text-right text-xs text-ink-400">{ago(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
