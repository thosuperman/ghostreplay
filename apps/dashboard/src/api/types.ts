// Mirrors packages/ghostreplay/src/ghostreplay/models (schema ghostreplay/v1).

export type EventKind =
  | "execution_start"
  | "model_call"
  | "tool_call"
  | "nondeterminism"
  | "agent_step"
  | "guard"
  | "state_snapshot"
  | "divergence"
  | "error"
  | "execution_end";

export type EventSource = "live" | "recorded" | "injected" | "simulated" | "framework";
export type ExecutionMode = "record" | "replay" | "counterfactual-replay" | "branch";
export type ExecutionStatus = "running" | "completed" | "failed" | "diverged";
export type InvariantStatus = "passed" | "failed" | "inconclusive";
export type ReplayVerdict = "matched" | "substituted" | "diverged" | "live";

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export interface ErrorInfo {
  type: string;
  message: string;
  retryable: boolean;
  data: Record<string, Json>;
}

export interface AppliedFault {
  fault_id: string;
  kind: string;
  title: string;
  strategy: string;
  description: string;
  operation_executed: boolean;
  original_response: Json;
  original_error: ErrorInfo | null;
}

export interface ReplayAnnotation {
  verdict: ReplayVerdict;
  recorded_event_id: string | null;
  recorded_seq: number | null;
  detail: string;
}

export interface GREvent {
  schema_version: string;
  execution_id: string;
  event_id: string;
  parent_event_id: string | null;
  seq: number;
  kind: EventKind;
  name: string;
  timestamp: string;
  duration_ms: number;
  agent: string | null;
  source: EventSource;
  model: string | null;
  request: Json;
  response: Json;
  error: ErrorInfo | null;
  state_before: Json;
  state_after: Json;
  match_key: string | null;
  destructive: boolean;
  fault: AppliedFault | null;
  replay: ReplayAnnotation | null;
  metadata: Record<string, Json>;
}

export interface Provenance {
  model_provider: string;
  model: string;
  model_is_live: boolean;
  label: string;
  tool_backends: string;
}

export interface AgentResult {
  status: "success" | "failed" | "escalated" | "partial" | "refused";
  message: string;
  data: Record<string, Json>;
}

export interface InvariantResult {
  id: string;
  title: string;
  status: InvariantStatus;
  severity: "critical" | "high" | "medium" | "low";
  message: string;
  explanation: string;
  evidence: string[];
}

export interface Divergence {
  type: "mismatch" | "unexpected_call" | "incomplete" | "result_mismatch";
  at_seq: number | null;
  recorded_seq: number | null;
  expected: Record<string, Json> | null;
  actual: Record<string, Json> | null;
  changes: Change[];
  message: string;
  after_fault: boolean;
}

export interface Change {
  path: string;
  op: "added" | "removed" | "changed";
  before: Json;
  after: Json;
}

export interface FaultTarget {
  kind: "tool_call" | "model_call";
  name: string;
  occurrence: number | null;
  where: Record<string, Json>;
}

export interface FaultSpec {
  id: string;
  kind: string;
  target: FaultTarget;
  params: Record<string, Json>;
  description: string;
}

export interface FaultPreset {
  id: string;
  title: string;
  summary: string;
  faults: FaultSpec[];
  expected_risk: string;
  headline: boolean;
}

export interface ExecutionSummary {
  id: string;
  app: string;
  scenario: string;
  variant: string;
  mode: ExecutionMode;
  status: ExecutionStatus;
  created_at: string;
  duration_ms: number;
  title: string;
  tool_calls: number;
  model_calls: number;
  errors: number;
  destructive_calls: number;
  injected_faults: number;
  invariants_failed: number;
  invariants_total: number;
  failed_invariants: string[];
  reference_execution_id: string | null;
  diverged: boolean;
  model_provider: string;
  output_status: string | null;
}

export interface Execution {
  schema_version: string;
  id: string;
  app: string;
  scenario: string;
  variant: string;
  agent: string;
  mode: ExecutionMode;
  status: ExecutionStatus;
  created_at: string;
  started_at: string;
  duration_ms: number;
  provenance: Provenance;
  task: Record<string, Json>;
  output: AgentResult | null;
  reference_execution_id: string | null;
  faults: FaultSpec[];
  conditions: Record<string, string>;
  events: GREvent[];
  final_state: Record<string, Json> | null;
  invariants: InvariantResult[];
  divergence: Divergence | null;
  notes: string[];
  title: string;
  summary: ExecutionSummary;
}

export interface Variant {
  id: string;
  title: string;
  description: string;
  is_fix: boolean;
}

export interface Condition {
  id: string;
  title: string;
  options: string[];
  default: string;
  incident: string;
  description: string;
}

export interface ToolSchema {
  name: string;
  description: string;
  category: string;
  destructive: boolean;
}

export interface Scenario {
  id: string;
  app: string;
  title: string;
  summary: string;
  bug_explanation: string;
  fix_explanation: string;
  headline_invariant: string;
  variants: Variant[];
  conditions: Condition[];
  invariants: { id: string; title: string; description: string; severity: string; requires_state: boolean }[];
  fault_presets: FaultPreset[];
  tools: ToolSchema[];
  default_task: Record<string, Json>;
}

export interface FaultKind {
  id: string;
  title: string;
  description: string;
  strategy: "error" | "transform" | "execute_then_error" | "delay";
  requires_branch: boolean;
  params: Record<string, string>;
}

export interface EventRef {
  event_id: string;
  seq: number;
  kind: string;
  name: string;
  source: string;
  error: string | null;
  destructive: boolean;
  injected: boolean;
}

export interface DiffEntry {
  type: string;
  kind: string;
  name: string;
  summary: string;
  a: EventRef | null;
  b: EventRef | null;
  changes: Change[];
}

export interface AlignedRow {
  index: number;
  status: "same" | "changed" | "added" | "removed";
  a: EventRef | null;
  b: EventRef | null;
  entries: number[];
}

export interface TraceDiff {
  a_id: string;
  b_id: string;
  identical: boolean;
  first_divergence: { row: number; a_seq: number | null; b_seq: number | null; summary: string } | null;
  rows: AlignedRow[];
  entries: DiffEntry[];
  behavior: {
    status: [string, string];
    output_status: [string | null, string | null];
    output_message: [string | null, string | null];
    tool_counts: Record<string, [number, number]>;
    destructive_calls: [number, number];
    errors: [number, number];
    invariants: { id: string; a: InvariantStatus | null; b: InvariantStatus | null; changed: boolean }[];
    final_state_changes: Change[];
  };
  counts: Record<string, number>;
}

export interface RegressionReport {
  case_id: string;
  title: string;
  app: string;
  scenario: string;
  variant: string;
  expect: "pass" | "fail";
  passed: boolean;
  outcome_matches_expectation: boolean;
  execution_id: string;
  mode: string;
  status: string;
  duration_ms: number;
  invariants: InvariantResult[];
  divergence: Divergence | null;
  notes: string[];
}

export interface DemoStep {
  id: string;
  title: string;
  narrative: string;
  execution_ids: string[];
  verdict: "pass" | "fail" | "info" | "diverged";
  expected: "pass" | "fail" | null;
  as_expected: boolean;
  data: Record<string, Json>;
}

export interface DemoStory {
  ok: boolean;
  scenario: string;
  app: string;
  title: string;
  steps: DemoStep[];
  reports: RegressionReport[];
}

export interface RunResult {
  execution: ExecutionSummary;
  diff: TraceDiff;
}

export interface ExportedCase {
  case: Record<string, Json>;
  case_file: string;
  test_file: string;
  pytest_source: string;
}

export interface LabInfo {
  app: string;
  version: string;
  schema_version: string;
  scenarios: { id: string; title: string }[];
  offline: boolean;
  public: boolean;
  can_clear: boolean;
  live_model: LiveModelInfo | null;
  storage: string;
  /** Public deployments: each browser session only sees the executions it created. */
  isolated_sessions?: boolean;
  session_ttl_hours?: number | null;
}

export interface LiveModelInfo {
  provider: string;
  model: string;
  effort: string;
  max_calls: number;
  sdk_installed: boolean;
}

export type ModelChoice = "scripted" | "live";

export interface ImportResult {
  execution: ExecutionSummary;
  replayable_here: boolean;
  note: string;
}
