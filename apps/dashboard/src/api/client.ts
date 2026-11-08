import type {
  DemoStory,
  Execution,
  ExecutionSummary,
  ExportedCase,
  ImportResult,
  FaultKind,
  FaultSpec,
  LabInfo,
  ModelChoice,
  RegressionReport,
  RunResult,
  Scenario,
  TraceDiff,
} from "./types";

export type LabId = "support" | "devops";

export interface LabDef {
  id: LabId;
  name: string;
  short: string;
  scenario: string;
  base: string;
  demoLabel: string;
  tagline: string;
}

export const LABS: Record<LabId, LabDef> = {
  support: {
    id: "support",
    name: "Support Agent Lab",
    short: "Support",
    scenario: "duplicate-refund",
    base: "/lab/support",
    demoLabel: "Try the Duplicate Refund Demo",
    tagline: "A refund times out after it committed. The retry pays the customer twice.",
  },
  devops: {
    id: "devops",
    name: "DevOps Agent Lab",
    short: "DevOps",
    scenario: "unsafe-infra-action",
    base: "/lab/devops",
    demoLabel: "Try the Unsafe Infrastructure Demo",
    tagline: "Stale health data on a simulated AWS fleet. The agent terminates healthy instances mid-incident.",
  },
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(lab: LabId, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${LABS[lab].base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail: string | null = null;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) detail = String((body as { detail: unknown }).detail);
    } catch {
      /* not JSON: usually the dev proxy failing to reach the lab server */
    }
    if (detail === null) {
      detail =
        res.status >= 500
          ? `${LABS[lab].name} is not reachable (HTTP ${res.status}). Locally, start it with ./scripts/dev.sh or: uv run ${lab}-agent-lab serve`
          : res.statusText || `HTTP ${res.status}`;
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const post = <T>(lab: LabId, path: string, body: unknown) =>
  request<T>(lab, path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  info: (lab: LabId) => request<LabInfo>(lab, "/api/info"),
  scenarios: (lab: LabId) => request<Scenario[]>(lab, "/api/scenarios"),
  faultKinds: (lab: LabId) => request<FaultKind[]>(lab, "/api/faults"),
  executions: (lab: LabId) => request<ExecutionSummary[]>(lab, "/api/executions?limit=200"),
  execution: (lab: LabId, id: string) => request<Execution>(lab, `/api/executions/${encodeURIComponent(id)}`),
  clear: (lab: LabId) => request<{ deleted: number }>(lab, "/api/executions", { method: "DELETE" }),
  record: (
    lab: LabId,
    scenario: string,
    variant: string,
    conditions: Record<string, string>,
    title = "",
    model: ModelChoice = "scripted",
  ) => post<ExecutionSummary>(lab, "/api/runs/record", { scenario, variant, conditions, title, model }),
  replay: (lab: LabId, executionId: string) => post<RunResult>(lab, "/api/runs/replay", { execution_id: executionId }),
  counterfactual: (
    lab: LabId,
    body: { execution_id: string; faults: FaultSpec[]; preset?: string | null; variant?: string | null; mode: string },
  ) => post<RunResult>(lab, "/api/runs/counterfactual", body),
  diff: (lab: LabId, a: string, b: string) =>
    request<TraceDiff>(lab, `/api/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  demo: (lab: LabId, scenario: string) => post<DemoStory>(lab, "/api/demo/prepare", { scenario }),
  runRegression: (lab: LabId, executionId: string) =>
    post<RegressionReport[]>(lab, "/api/regression/run", { execution_id: executionId }),
  exportCase: (lab: LabId, executionId: string, variant: string) =>
    post<ExportedCase>(lab, "/api/regression/export", { execution_id: executionId, variant }),
  imported: (lab: LabId) => request<ExecutionSummary[]>(lab, "/api/executions?imported=true&limit=100"),
  importTrace: (lab: LabId, body: string) =>
    request<ImportResult>(lab, "/api/traces/import", { method: "POST", headers: { "Content-Type": "application/json" }, body }),
  traceUrl: (lab: LabId, executionId: string) => `${LABS[lab].base}/api/executions/${encodeURIComponent(executionId)}/trace`,
  replayStreamUrl: (lab: LabId, executionId: string, delayMs: number) =>
    `${LABS[lab].base}/api/executions/${encodeURIComponent(executionId)}/replay/stream?delay_ms=${delayMs}`,
};
