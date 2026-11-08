import type { Execution, ExecutionSummary } from "../api/types";

export type TypeTone = "violet" | "cyan" | "amber" | "red" | "green" | "neutral";
export interface ExecType {
  label: string;
  tone: TypeTone;
  detail: string;
}

const INCIDENT: Record<string, string> = {
  timeout_after_commit: "refund service delays its response after committing (injected)",
  stale: "monitoring serves a stale health snapshot (injected)",
};

/** What kind of execution this is, derived only from the stored execution record. */
export function executionTypes(
  e: Pick<Execution, "mode" | "variant" | "faults" | "conditions" | "provenance" | "reference_execution_id" | "events"> | ExecutionSummaryLike,
  opts: { library?: boolean } = {},
): ExecType[] {
  const out: ExecType[] = [];
  const full = "provenance" in e;
  const provider = full ? e.provenance.model_provider : e.model_provider;
  const live = full ? e.provenance.model_is_live : provider !== "scripted" && e.mode === "record";
  const fromCapture = full ? e.provenance.label.includes("genuine capture") : provider !== "scripted" && e.mode === "branch";
  const faults = full ? e.faults.length + (e as Execution).events.filter((ev) => ev.fault).length : e.injected_faults;

  if (opts.library) out.push({ label: "Genuine capture", tone: "violet", detail: "Recorded with a live model against real local services; shipped read-only." });
  if (e.mode === "replay") {
    out.push({ label: "Strict offline replay", tone: "cyan", detail: "Every model and tool call was served from the recording. Nothing was executed." });
  } else if (e.mode === "counterfactual-replay") {
    out.push({ label: "Controlled fault injection · offline", tone: "amber", detail: "Recording replayed offline with an injected fault; stops at the first divergence." });
  } else if (e.mode === "branch") {
    if (faults) out.push({ label: "Controlled fault injection", tone: "amber", detail: "A labelled fault was injected; the run then re-executed for real." });
    if (fromCapture)
      out.push(
        e.variant === "fixed"
          ? { label: "Corrected re-execution", tone: "green", detail: "The corrected app ran again for real; model decisions were served from its genuine capture." }
          : { label: "Re-execution · recorded decisions", tone: "cyan", detail: "Tools, HTTP and SQL ran again for real; model decisions were served from the genuine capture (no model call)." },
      );
    else out.push({ label: "Re-execution", tone: "cyan", detail: "Replayed up to the fault, then re-executed against fresh services." });
  } else {
    out.push(
      live
        ? { label: "Live LLM execution", tone: "violet", detail: `A live model (${provider}) chose the tools; tools ran against real local services.` }
        : { label: "Scripted demo", tone: "neutral", detail: "Decisions came from a deterministic scripted policy, not an LLM. Tools still ran for real." },
    );
    if (faults) out.push({ label: "Controlled fault injection", tone: "amber", detail: "A labelled fault was injected into a tool call." });
  }
  if (full) {
    for (const v of Object.values(e.conditions ?? {})) {
      if (INCIDENT[v]) out.push({ label: "Controlled fault", tone: "amber", detail: INCIDENT[v] });
    }
  }
  return out;
}

type ExecutionSummaryLike = Pick<ExecutionSummary, "mode" | "variant" | "model_provider" | "injected_faults" | "reference_execution_id">;
