import { useMemo, useState } from "react";
import type { LabId } from "../api/client";
import type { Execution, ExecutionSummary, GREvent, InvariantResult } from "../api/types";
import { describe, ms, offset, shortId } from "../lib/format";
import { href } from "../lib/router";
import {
  Badge,
  cx,
  InvariantBadge,
  JsonView,
  KindIcon,
  ModeBadge,
  Select,
  SourceBadge,
  Verdict,
  VerdictChip,
} from "./ui";

/* ------------------------------------------------------------------------------------ */
/* Timeline                                                                             */
/* ------------------------------------------------------------------------------------ */

const HIDDEN_BY_DEFAULT = new Set(["nondeterminism", "state_snapshot", "execution_start", "execution_end"]);

export function Timeline({ execution, selected, onSelect, highlight = [], compact = false }: {
  execution: Execution;
  selected?: string;
  onSelect?: (e: GREvent) => void;
  highlight?: string[];
  compact?: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const events = useMemo(
    () => execution.events.filter((e) => showAll || !HIDDEN_BY_DEFAULT.has(e.kind)),
    [execution, showAll],
  );
  const total = Math.max(
    1,
    ...execution.events.map((e) => offset(e, execution.started_at) + e.duration_ms),
  );
  const hl = new Set(highlight);
  return (
    <div>
      {!compact && (
        <div className="flex items-center justify-between border-b hairline px-4 py-2 text-[11px] text-ink-400">
          <span>
            {events.length} of {execution.events.length} events · simulated time {ms(total)}
          </span>
          <label className="flex cursor-pointer items-center gap-1.5 hover:text-ink-200">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-violet-500" />
            show clock / id / snapshot events
          </label>
        </div>
      )}
      <ol className="relative">
        {events.map((e, i) => {
          const start = offset(e, execution.started_at);
          const left = (start / total) * 100;
          const width = Math.max(0.6, (e.duration_ms / total) * 100);
          const danger = e.destructive && !e.error;
          const isSel = selected === e.event_id;
          return (
            <li
              key={e.event_id}
              style={{ animationDelay: `${Math.min(i, 30) * 18}ms` }}
              className={cx(
                "group relative animate-rise border-b hairline last:border-b-0",
                onSelect && "cursor-pointer",
                isSel ? "bg-violet-500/[0.08]" : hl.has(e.event_id) ? "bg-rose-500/[0.06]" : "hover:bg-white/[0.025]",
              )}
              onClick={() => onSelect?.(e)}
            >
              {isSel && <span className="absolute inset-y-0 left-0 w-0.5 bg-violet-400" />}
              <div className={cx("flex items-start gap-3 px-4", compact ? "py-1.5" : "py-2.5")}>
                <span className="w-14 shrink-0 pt-1 text-right font-mono text-[10.5px] text-ink-400">+{ms(start)}</span>
                <KindIcon kind={e.kind} danger={danger} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={cx("font-mono text-[12.5px] font-medium", e.error ? "text-rose-200" : "text-ink-100")}>
                      {e.name}
                    </span>
                    {e.destructive && <Badge tone="red">destructive</Badge>}
                    {e.error && <Badge tone="red">{e.error.type}</Badge>}
                    {e.fault && <Badge tone="fuchsia">⚡ {e.fault.title}</Badge>}
                    {e.kind === "guard" && <Badge tone="green">blocked</Badge>}
                    {e.kind === "divergence" && <Badge tone="amber">divergence</Badge>}
                    {!compact && e.kind !== "divergence" && e.kind !== "guard" && e.kind !== "agent_step" && <SourceBadge source={e.source} />}
                    {!compact && e.replay && e.replay.verdict !== "matched" && <VerdictChip verdict={e.replay.verdict} />}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[11px] text-ink-400">{describe(e)}</div>
                </div>
                {!compact && (
                  <div className="hidden w-40 shrink-0 pt-1.5 lg:block">
                    <div className="relative h-1.5 rounded-full bg-white/[0.04]">
                      <div
                        className={cx(
                          "absolute h-1.5 rounded-full",
                          e.error ? "bg-rose-400" : e.fault ? "bg-fuchsia-400" : e.kind === "model_call" ? "bg-violet-400" : "bg-sky-400/80",
                        )}
                        style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                      />
                    </div>
                    <div className="mt-1 text-right font-mono text-[10px] text-ink-500">{e.duration_ms ? ms(e.duration_ms) : ""}</div>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ------------------------------------------------------------------------------------ */
/* Inspector                                                                            */
/* ------------------------------------------------------------------------------------ */

type Tab = "request" | "response" | "state" | "fault" | "replay" | "raw";

export function Inspector({ event }: { event: GREvent | undefined }) {
  const [tab, setTab] = useState<Tab>("request");
  if (!event) {
    return <div className="p-6 text-sm text-ink-400">Select an event in the timeline to inspect its inputs, outputs, state and errors.</div>;
  }
  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "request", label: event.kind === "model_call" ? "Prompt" : "Request", show: true },
    { id: "response", label: event.error ? "Error" : "Response", show: true },
    { id: "state", label: "State", show: event.state_before !== null || event.state_after !== null },
    { id: "fault", label: "Fault", show: event.fault !== null },
    { id: "replay", label: "Replay", show: event.replay !== null },
    { id: "raw", label: "Raw", show: true },
  ];
  const active = tabs.find((t) => t.id === tab && t.show) ? tab : "request";
  return (
    <div className="flex min-h-0 flex-col">
      <div className="border-b hairline px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <KindIcon kind={event.kind} danger={event.destructive && !event.error} />
          <span className="font-mono text-sm font-semibold text-white">{event.name}</span>
          <SourceBadge source={event.source} />
          {event.destructive && <Badge tone="red">destructive</Badge>}
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-[11px] text-ink-400">
          <span>seq {event.seq}</span>
          <span>{ms(event.duration_ms)}</span>
          <span className="truncate" title={event.event_id}>{shortId(event.event_id)}</span>
          {event.parent_event_id && <span className="col-span-3 truncate">parent {event.parent_event_id}</span>}
          {event.match_key && <span className="col-span-3 truncate" title="hash of kind + name + redacted request, used for replay matching">match key {event.match_key}</span>}
        </div>
      </div>
      <div className="flex gap-1 border-b hairline px-3 py-1.5">
        {tabs.filter((t) => t.show).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cx(
              "rounded-md px-2.5 py-1 text-xs font-medium",
              active === t.id ? "bg-white/[0.08] text-white" : "text-ink-300 hover:text-white",
              t.id === "fault" && "text-fuchsia-300",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="space-y-3 overflow-auto p-4">
        {active === "request" && <JsonView value={event.request} />}
        {active === "response" &&
          (event.error ? (
            <div className="space-y-2">
              <div className="rounded-lg border border-rose-400/30 bg-rose-500/[0.07] p-3">
                <div className="font-mono text-sm font-semibold text-rose-200">{event.error.type}</div>
                <div className="mt-1 text-sm text-rose-100/80">{event.error.message}</div>
                <div className="mt-2 text-xs text-rose-200/60">retryable: {String(event.error.retryable)}</div>
              </div>
              {Object.keys(event.error.data).length > 0 && <JsonView value={event.error.data} />}
            </div>
          ) : (
            <JsonView value={event.response} />
          ))}
        {active === "state" && (
          <div className="grid gap-3">
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Before</div>
              <JsonView value={event.state_before} maxHeight="14rem" />
            </div>
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">After</div>
              <JsonView value={event.state_after} maxHeight="14rem" />
            </div>
            <p className="text-[11px] text-ink-400">Only explicitly observable simulated state is captured. Nothing is inferred.</p>
          </div>
        )}
        {active === "fault" && event.fault && (
          <div className="space-y-3">
            <div className="rounded-lg border border-fuchsia-400/30 bg-fuchsia-500/[0.07] p-3 text-sm">
              <div className="font-semibold text-fuchsia-200">⚡ {event.fault.title}</div>
              <div className="mt-1 text-fuchsia-100/80">{event.fault.description}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge tone="fuchsia">strategy: {event.fault.strategy}</Badge>
                <Badge tone={event.fault.operation_executed && event.destructive ? "red" : "neutral"}>
                  {event.fault.operation_executed
                    ? event.destructive
                      ? "operation executed · side effect committed"
                      : "real call executed"
                    : "operation not executed"}
                </Badge>
              </div>
            </div>
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Original (unfaulted) response</div>
              <JsonView value={event.fault.original_error ? { error: event.fault.original_error as unknown as never } : event.fault.original_response} maxHeight="16rem" />
            </div>
          </div>
        )}
        {active === "replay" && event.replay && (
          <div className="space-y-2 text-sm">
            <VerdictChip verdict={event.replay.verdict} />
            {event.replay.recorded_event_id && (
              <div className="font-mono text-xs text-ink-300">recorded event {event.replay.recorded_event_id} (seq {event.replay.recorded_seq})</div>
            )}
            {event.replay.detail && <div className="text-ink-200">{event.replay.detail}</div>}
          </div>
        )}
        {active === "raw" && <JsonView value={event as unknown as never} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------ */
/* Invariants                                                                           */
/* ------------------------------------------------------------------------------------ */

export function InvariantList({ invariants, onEvidence, dense = false }: {
  invariants: InvariantResult[];
  onEvidence?: (eventId: string) => void;
  dense?: boolean;
}) {
  if (invariants.length === 0) return <div className="p-4 text-sm text-ink-400">No invariants evaluated.</div>;
  const order = { failed: 0, inconclusive: 1, passed: 2 } as const;
  const sorted = [...invariants].sort((a, b) => order[a.status] - order[b.status]);
  return (
    <ul className="divide-y divide-white/[0.06]">
      {sorted.map((inv) => (
        <li key={inv.id} className={cx("px-4", dense ? "py-2" : "py-3", inv.status === "failed" && "bg-rose-500/[0.04]")}>
          <div className="flex items-start gap-3">
            <div className="pt-0.5">
              <InvariantBadge status={inv.status} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-medium text-ink-100">{inv.title}</span>
                <span className="font-mono text-[10.5px] text-ink-400">{inv.id}</span>
                {inv.severity === "critical" && inv.status === "failed" && <Badge tone="red">critical</Badge>}
              </div>
              <div className={cx("mt-0.5 text-[12.5px]", inv.status === "failed" ? "text-rose-200" : "text-ink-300")}>{inv.message}</div>
              {!dense && inv.status === "failed" && inv.explanation && (
                <div className="mt-1.5 rounded-md border-l-2 border-rose-400/50 bg-white/[0.02] px-2.5 py-1.5 text-[12px] leading-relaxed text-ink-200">
                  {inv.explanation}
                </div>
              )}
              {!dense && onEvidence && inv.evidence.length > 0 && inv.status !== "passed" && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {inv.evidence.slice(0, 6).map((id) => (
                    <button key={id} onClick={() => onEvidence(id)} className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[10.5px] text-ink-300 hover:bg-white/10 hover:text-white">
                      seq {id.split(".").pop()?.replace(/^0+/, "") || "0"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function verdictOf(summary: Pick<ExecutionSummary, "invariants_failed" | "status">): "pass" | "fail" | "diverged" {
  if (summary.invariants_failed > 0) return "fail";
  if (summary.status === "diverged") return "diverged";
  return "pass";
}

export function ExecutionHeaderLine({ lab, s }: { lab: LabId; s: ExecutionSummary }) {
  return (
    <a href={href({ name: "execution", lab, id: s.id })} className="group flex min-w-0 items-center gap-2">
      <Verdict verdict={verdictOf(s)} />
      <span className="truncate text-[13px] text-ink-100 group-hover:text-white">{s.title || s.id}</span>
      <ModeBadge mode={s.mode} />
      <Badge>{s.variant}</Badge>
    </a>
  );
}

export function ExecutionPicker({ executions, value, onChange, label, filter }: {
  executions: ExecutionSummary[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  filter?: (s: ExecutionSummary) => boolean;
}) {
  const list = filter ? executions.filter(filter) : executions;
  return (
    <Select
      label={label}
      value={value}
      onChange={onChange}
      options={[
        { value: "", label: "— choose an execution —" },
        ...list.map((s) => ({
          value: s.id,
          label: `${verdictOf(s).toUpperCase()} · ${s.title || s.id} · ${s.variant} · ${s.mode} · ${s.id}`,
        })),
      ]}
    />
  );
}
