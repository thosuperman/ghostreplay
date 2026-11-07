import type { GREvent, Json } from "../api/types";
import { jsonDiff } from "../lib/jsondiff";
import { Badge, cx, JsonView } from "./ui";

/** Shows what fault injection changed on one event: field-level diff + both payloads. */
export function FaultSummary({ event }: { event: GREvent }) {
  const fault = event.fault;
  if (!fault) return null;
  const seen: Json = event.error ? { error: event.error.type, message: event.error.message } : event.response;
  const changes = event.error ? [] : jsonDiff(fault.original_response, event.response);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <Badge tone="fuchsia">⚡ {fault.title}</Badge>
        <span className="font-mono text-ink-200">{event.name}</span>
        <span className="text-ink-400">seq {event.seq}</span>
        {fault.operation_executed ? (
          event.destructive ? <Badge tone="red">side effect committed</Badge> : <Badge>real call executed</Badge>
        ) : (
          <Badge>operation not executed</Badge>
        )}
      </div>
      {changes.length > 0 && (
        <div className="rounded-lg border border-fuchsia-400/25 bg-fuchsia-500/[0.05] px-3 py-2 font-mono text-[11.5px]">
          {changes.slice(0, 8).map((c) => (
            <div key={c.path} className="flex flex-wrap gap-2">
              <span className="text-fuchsia-200">{c.path}</span>
              <span className={cx("text-rose-200/80", c.op !== "added" && "line-through decoration-rose-400/40")}>{c.op === "added" ? "" : JSON.stringify(c.before)}</span>
              <span className="text-ink-500">→</span>
              <span className="text-emerald-200">{c.op === "removed" ? "(removed)" : JSON.stringify(c.after)}</span>
            </div>
          ))}
          {changes.length > 8 && <div className="text-ink-400">+{changes.length - 8} more</div>}
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Real / recorded response</div>
          <JsonView value={fault.original_error ? { error: fault.original_error.type, message: fault.original_error.message } : fault.original_response} maxHeight="11rem" />
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-fuchsia-300">What the agent saw</div>
          <JsonView value={seen} maxHeight="11rem" className="border-fuchsia-400/30" />
        </div>
      </div>
    </div>
  );
}
