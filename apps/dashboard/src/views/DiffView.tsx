import { Fragment, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { AlignedRow, Change, EventRef, TraceDiff } from "../api/types";
import { ExecutionPicker } from "../components/execution";
import { Badge, Card, cx, Empty, ErrorBox, Loading, SectionHeader, Verdict } from "../components/ui";
import { navigate } from "../lib/router";
import { useAsync } from "../lib/useAsync";

export function DiffView({ lab, a, b }: { lab: LabId; a?: string; b?: string }) {
  const list = useAsync(() => api.executions(lab), [lab]);
  const diff = useAsync<TraceDiff | undefined>(() => (a && b ? api.diff(lab, a, b) : Promise.resolve(undefined)), [lab, a, b]);
  const [open, setOpen] = useState<number | null>(null);

  const set = (na?: string, nb?: string) => navigate({ name: "diff", lab, a: na || undefined, b: nb || undefined });
  const d = diff.data;
  const expanded = open ?? d?.first_divergence?.row ?? null;

  return (
    <div className="animate-fade">
      <SectionHeader eyebrow={LABS[lab].name} title="Structural Diff">
        Interactions are aligned by signature (kind + name), then compared field by field: arguments, results, errors, model inputs and
        outputs. Timestamps and ids never cause noise.
      </SectionHeader>

      <Card className="mb-5">
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <ExecutionPicker label="A (left)" executions={list.data ?? []} value={a ?? ""} onChange={(v) => set(v, b)} />
          <ExecutionPicker label="B (right)" executions={list.data ?? []} value={b ?? ""} onChange={(v) => set(a, v)} />
        </div>
      </Card>

      {!(a && b) && <Empty title="Pick two executions">Tip: compare the vulnerable and fixed counterfactuals from the guided demo.</Empty>}
      {diff.error && <ErrorBox error={diff.error} />}
      {diff.loading && a && b && <Loading label="Computing structural diff…" />}

      {d && (
        <div className="space-y-5">
          <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
            <Card title="Summary">
              <div className="space-y-3 p-4">
                <div className="flex items-center gap-3">
                  <Verdict verdict={d.identical ? "pass" : "diverged"} size="lg" />
                  <span className="text-sm text-ink-100">{d.identical ? "Structurally identical" : `${d.entries.length} structural differences`}</span>
                </div>
                {d.first_divergence && (
                  <div className="rounded-lg border border-amber-400/25 bg-amber-400/[0.05] p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">First divergence · row {d.first_divergence.row}</div>
                    <div className="mt-1 font-mono text-[12.5px] text-amber-100">{d.first_divergence.summary}</div>
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(d.counts).map(([k, v]) => <Badge key={k} tone={k.startsWith("added") ? "green" : k.startsWith("removed") ? "red" : "amber"}>{k.replace(/_/g, " ")} · {v}</Badge>)}
                </div>
              </div>
            </Card>
            <Card title="Behavioural differences">
              <table className="w-full text-[12.5px]">
                <thead className="text-[10.5px] uppercase tracking-wider text-ink-400">
                  <tr><th className="px-4 py-2 text-left font-medium">Signal</th><th className="px-4 py-2 text-left font-medium">A</th><th className="px-4 py-2 text-left font-medium">B</th></tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  <Row label="status" a={d.behavior.status[0]} b={d.behavior.status[1]} />
                  <Row label="agent outcome" a={d.behavior.output_status[0]} b={d.behavior.output_status[1]} />
                  <Row label="destructive side effects committed" a={d.behavior.destructive_calls[0]} b={d.behavior.destructive_calls[1]} danger />
                  <Row label="tool errors" a={d.behavior.errors[0]} b={d.behavior.errors[1]} />
                  {Object.entries(d.behavior.tool_counts).filter(([, [x, y]]) => x !== y).map(([name, [x, y]]) => <Row key={name} label={`calls · ${name}`} a={x} b={y} />)}
                  {d.behavior.invariants.filter((i) => i.changed).map((i) => <Row key={i.id} label={i.id} a={i.a} b={i.b} />)}
                </tbody>
              </table>
            </Card>
          </div>

          <Card title="Side-by-side interactions" subtitle="Click a changed row to see field-level differences">
            <div className="grid grid-cols-[1fr_2.5rem_1fr] border-b hairline bg-white/[0.02] px-4 py-2 text-[10.5px] uppercase tracking-wider text-ink-400">
              <span>A · <span className="font-mono normal-case">{d.a_id}</span></span><span />
              <span>B · <span className="font-mono normal-case">{d.b_id}</span></span>
            </div>
            {d.rows.map((row) => (
              <Fragment key={row.index}>
                <DiffRow row={row} first={d.first_divergence?.row === row.index} open={expanded === row.index} onClick={() => setOpen(expanded === row.index ? -1 : row.index)} />
                {expanded === row.index && row.entries.length > 0 && (
                  <div className="animate-fade border-b hairline bg-ink-950/70 px-4 py-3">
                    {row.entries.map((ix) => {
                      const entry = d.entries[ix];
                      if (!entry) return null;
                      return (
                        <div key={ix} className="mb-3 last:mb-0">
                          <div className="mb-1 text-[12px] font-medium text-amber-200">{entry.summary}</div>
                          <Changes changes={entry.changes} />
                        </div>
                      );
                    })}
                  </div>
                )}
              </Fragment>
            ))}
          </Card>

          {(d.behavior.output_message[0] !== d.behavior.output_message[1] || d.behavior.final_state_changes.length > 0) && (
            <div className="grid gap-5 lg:grid-cols-2">
              <Card title="Final agent message">
                <div className="grid gap-3 p-4 text-[12.5px]">
                  <div><Badge>A</Badge> <span className="text-ink-200">{d.behavior.output_message[0] ?? "—"}</span></div>
                  <div><Badge>B</Badge> <span className="text-ink-200">{d.behavior.output_message[1] ?? "—"}</span></div>
                </div>
              </Card>
              <Card title="Final state changes" subtitle="Observable simulated state, A → B">
                <div className="p-4"><Changes changes={d.behavior.final_state_changes} /></div>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, a, b, danger }: { label: string; a: string | number | null; b: string | number | null; danger?: boolean }) {
  const changed = a !== b;
  return (
    <tr className={cx(changed && "bg-amber-400/[0.03]")}>
      <td className="px-4 py-1.5 font-mono text-ink-300">{label}</td>
      <td className={cx("px-4 py-1.5 font-mono", danger && Number(a) > 0 ? "text-rose-300" : "text-ink-100")}>{a ?? "—"}</td>
      <td className={cx("px-4 py-1.5 font-mono", danger && Number(b) > 0 ? "text-rose-300" : changed ? "text-amber-200" : "text-ink-100")}>{b ?? "—"}</td>
    </tr>
  );
}

function Cell({ ev, side }: { ev: EventRef | null; side: "a" | "b" }) {
  if (!ev) return <div className={cx("h-full rounded-md border border-dashed border-white/[0.06]", side === "a" ? "bg-rose-500/[0.02]" : "bg-emerald-500/[0.02]")} />;
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1">
      <span className="w-7 font-mono text-[10px] text-ink-500">{ev.seq}</span>
      <span className="truncate font-mono text-[12px] text-ink-100">{ev.name}</span>
      <span className="text-[10px] text-ink-500">{ev.kind.replace("_call", "")}</span>
      {ev.destructive && <Badge tone="red">destructive</Badge>}
      {ev.error && <Badge tone="red">{ev.error}</Badge>}
      {ev.injected && <Badge tone="fuchsia">⚡</Badge>}
    </div>
  );
}

function DiffRow({ row, first, open, onClick }: { row: AlignedRow; first: boolean; open: boolean; onClick: () => void }) {
  const marker = { same: "=", changed: "≠", added: "+", removed: "−" }[row.status];
  const tone = {
    same: "",
    changed: "bg-amber-400/[0.05]",
    added: "bg-emerald-400/[0.05]",
    removed: "bg-rose-500/[0.05]",
  }[row.status];
  return (
    <div
      onClick={row.entries.length ? onClick : undefined}
      className={cx("relative grid grid-cols-[1fr_2.5rem_1fr] items-center border-b hairline px-4 py-1", tone, row.entries.length > 0 && "cursor-pointer hover:brightness-125", open && "ring-1 ring-inset ring-amber-400/30")}
    >
      {first && <span className="absolute -left-px top-0 h-full w-0.5 bg-amber-400" />}
      <Cell ev={row.a} side="a" />
      <span className={cx("text-center font-mono text-sm", row.status === "same" ? "text-ink-500" : row.status === "added" ? "text-emerald-300" : row.status === "removed" ? "text-rose-300" : "text-amber-300")}>
        {marker}
      </span>
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1"><Cell ev={row.b} side="b" /></div>
        {first && <Badge tone="amber">first divergence</Badge>}
      </div>
    </div>
  );
}

function Changes({ changes }: { changes: Change[] }) {
  if (changes.length === 0) return <span className="text-xs text-ink-400">No field-level changes.</span>;
  return (
    <div className="space-y-1 font-mono text-[11.5px]">
      {changes.map((c, i) => (
        <div key={`${c.path}-${i}`} className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-3">
          <span className={cx(c.op === "added" ? "text-emerald-300" : c.op === "removed" ? "text-rose-300" : "text-amber-300")}>
            {c.op === "added" ? "+" : c.op === "removed" ? "−" : "~"} {c.path}
          </span>
          <span className="min-w-0 break-all text-ink-300">
            {c.op !== "added" && <span className="text-rose-200/80 line-through decoration-rose-400/40">{trim(c.before)}</span>}
            {c.op === "changed" && <span className="mx-1.5 text-ink-500">→</span>}
            {c.op !== "removed" && <span className="text-emerald-200">{trim(c.after)}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function trim(v: unknown): string {
  const s = JSON.stringify(v);
  return s && s.length > 160 ? `${s.slice(0, 160)}…` : (s ?? "null");
}
