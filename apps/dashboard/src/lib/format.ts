import type { GREvent, Json } from "../api/types";

export function ms(value: number): string {
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(value < 10_000 ? 2 : 1)} s`;
  return `${(value / 60_000).toFixed(1)} min`;
}

export function offset(event: GREvent, startedAt: string): number {
  return new Date(event.timestamp).getTime() - new Date(startedAt).getTime();
}

export function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function shortId(id: string): string {
  return id.length > 14 ? `${id.slice(0, 14)}…` : id;
}

export function preview(value: Json, max = 80): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function isRecord(value: unknown): value is Record<string, Json> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** One-line human description of an event for timelines and diffs. */
export function describe(event: GREvent): string {
  const req = event.request;
  switch (event.kind) {
    case "tool_call": {
      if (isRecord(req)) {
        const parts = Object.entries(req)
          .slice(0, 3)
          .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`);
        return parts.join(" ").slice(0, 110);
      }
      return "";
    }
    case "model_call": {
      const resp = event.response;
      if (isRecord(resp)) {
        const calls = resp.tool_calls;
        if (Array.isArray(calls) && calls.length > 0) {
          const names = calls.map((c) => (isRecord(c) ? String(c.name) : "?")).join(", ");
          return `→ requests ${names}`;
        }
        if (typeof resp.content === "string") return `→ “${resp.content.slice(0, 96)}${resp.content.length > 96 ? "…" : ""}”`;
      }
      return "";
    }
    case "nondeterminism":
      return `= ${preview(event.response, 60)}`;
    case "agent_step":
    case "guard":
      return preview(req, 110);
    case "divergence":
      return isRecord(event.response) ? String(event.response.message ?? "") : "";
    case "state_snapshot":
      return "observable simulated state";
    case "execution_end":
      return isRecord(event.response) ? `status ${String(event.response.status ?? "")}` : event.name;
    default:
      return "";
  }
}
