import { useEffect, useMemo, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { Execution, FaultKind, FaultSpec, GREvent, Json, RunResult, Scenario } from "../api/types";
import { ExecutionPicker, InvariantList } from "../components/execution";
import { FaultSummary } from "../components/FaultSummary";
import { Badge, Button, Card, cx, Empty, ErrorBox, KindIcon, ModeBadge, SectionHeader, Select, Spinner, Verdict } from "../components/ui";
import { describe } from "../lib/format";
import { href } from "../lib/router";
import { useAsync } from "../lib/useAsync";

const DEFAULT_PARAMS: Record<string, Json> = {
  tool_timeout: {},
  timeout_after_commit: {},
  http_429: { retry_after_s: 2 },
  http_500: {},
  auth_failure: {},
  permission_denied: {},
  missing_field: { path: "" },
  null_value: { path: "" },
  duplicate_response: {},
  stale_data: { set: {} },
  incorrect_output: { set: {} },
  delayed_operation: { delay_ms: 15000 },
  partial_success: { message: "operation partially failed" },
};

type Mode = "auto" | "replay" | "branch";

export function FailureLab({ lab, initialId }: { lab: LabId; initialId?: string }) {
  const list = useAsync(() => api.executions(lab), [lab]);
  const kinds = useAsync(() => api.faultKinds(lab), [lab]);
  const scenarios = useAsync(() => api.scenarios(lab), [lab]);
  const [refId, setRefId] = useState(initialId ?? "");
  const [reference, setReference] = useState<Execution>();
  const [target, setTarget] = useState<GREvent>();
  const [kind, setKind] = useState("timeout_after_commit");
  const [params, setParams] = useState("{}");
  const [variant, setVariant] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [preset, setPreset] = useState<string>();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult>();
  const [resultEx, setResultEx] = useState<Execution>();
  const [error, setError] = useState<string>();

  const sc: Scenario | undefined = scenarios.data?.[0];

  useEffect(() => {
    if (!refId && list.data) {
      const first = list.data.find((s) => s.mode === "record" && s.invariants_failed === 0) ?? list.data.find((s) => s.mode === "record");
      if (first) setRefId(first.id);
    }
  }, [list.data, refId]);

  useEffect(() => {
    setReference(undefined);
    setTarget(undefined);
    setResult(undefined);
    if (refId) {
      api.execution(lab, refId).then((ex) => {
        setReference(ex);
        setVariant(ex.variant);
      }).catch((e: unknown) => setError(String(e)));
    }
  }, [lab, refId]);

  const targets = useMemo(() => reference?.events.filter((e) => e.kind === "tool_call" || e.kind === "model_call") ?? [], [reference]);
  const occurrence = (e: GREvent) => targets.filter((t) => t.name === e.name && t.seq <= e.seq).length;
  const kindDef: FaultKind | undefined = kinds.data?.find((k) => k.id === kind);

  const pickKind = (k: string) => {
    setKind(k);
    setPreset(undefined);
    setParams(JSON.stringify(DEFAULT_PARAMS[k] ?? {}, null, 2));
  };

  const applyPreset = (id: string) => {
    const p = sc?.fault_presets.find((x) => x.id === id);
    const f = p?.faults[0];
    if (!p || !f) return;
    setPreset(id);
    setKind(f.kind);
    setParams(JSON.stringify(f.params, null, 2));
    const t = targets.filter((e) => e.name === f.target.name)[(f.target.occurrence ?? 1) - 1] ?? targets.find((e) => e.name === f.target.name);
    setTarget(t);
  };

  const run = async (forceMode?: Mode) => {
    if (!reference) return;
    setRunning(true);
    setError(undefined);
    setResult(undefined);
    setResultEx(undefined);
    try {
      let faults: FaultSpec[] = [];
      let presetId: string | null = null;
      if (preset) {
        presetId = preset;
      } else {
        if (!target) throw new Error("Select the event to break in the recorded timeline.");
        let parsed: Record<string, Json>;
        try {
          parsed = JSON.parse(params) as Record<string, Json>;
        } catch {
          throw new Error("Fault parameters must be valid JSON.");
        }
        faults = [{
          id: `ui-${kind}-${target.seq}`,
          kind,
          target: { kind: target.kind === "model_call" ? "model_call" : "tool_call", name: target.name, occurrence: occurrence(target), where: {} },
          params: parsed,
          description: "",
        }];
      }
      const res = await api.counterfactual(lab, { execution_id: reference.id, faults, preset: presetId, variant, mode: forceMode ?? mode });
      setResult(res);
      setResultEx(await api.execution(lab, res.execution.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const injected = resultEx?.events.find((e) => e.fault);
  return (
    <div className="animate-fade">
      <SectionHeader eyebrow={LABS[lab].name} title="Counterfactual Failure Lab">
        Take a recorded execution, break one step on purpose, and see whether the agent stays safe. Faults that only change what the agent
        sees can run fully offline; faults that need a real side effect (e.g. <em>timeout after commit</em>) require <strong>branch execution</strong>{" "}
        against a fresh simulated environment. GhostReplay never invents a continuation.
      </SectionHeader>

      <Card className="mb-5">
        <div className="grid gap-4 p-4 md:grid-cols-[2fr_1fr_1fr]">
          <ExecutionPicker label="Recorded execution" executions={list.data ?? []} value={refId} onChange={setRefId} filter={(s) => s.mode === "record"} />
          <Select label="Agent variant under test" value={variant} onChange={setVariant} options={(sc?.variants ?? []).map((v) => ({ value: v.id, label: `${v.title} (${v.id})` }))} />
          <Select
            label="Execution mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "auto", label: "Auto (branch only if required)" },
              { value: "replay", label: "Strict offline counterfactual" },
              { value: "branch", label: "Branch execution (simulated)" },
            ]}
          />
        </div>
        {sc && (
          <div className="flex flex-wrap items-center gap-2 border-t hairline px-4 py-3">
            <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Presets</span>
            {sc.fault_presets.map((p) => (
              <button
                key={p.id}
                onClick={() => applyPreset(p.id)}
                aria-label={p.title}
                title={`${p.summary} Risk: ${p.expected_risk}`}
                className={cx(
                  "rounded-full px-3 py-1 text-xs ring-1 ring-inset transition-colors",
                  preset === p.id ? "bg-fuchsia-500/20 text-fuchsia-100 ring-fuchsia-400/50" : "text-ink-200 ring-white/10 hover:bg-white/5",
                )}
              >
                {p.headline && "★ "}{p.title}
              </button>
            ))}
          </div>
        )}
      </Card>

      {!refId && list.data && <Empty title="No recordings to break yet">Record a run first (Executions → Record run).</Empty>}

      {reference && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card title="1 · Choose the step to break" subtitle="Interactions from the recording (tool and model calls)">
            <ol className="max-h-[34rem] overflow-auto">
              {targets.map((e) => {
                const sel = target?.event_id === e.event_id;
                return (
                  <li
                    key={e.event_id}
                    onClick={() => { setTarget(e); setPreset(undefined); }}
                    className={cx("flex cursor-pointer items-center gap-3 border-b hairline px-4 py-2", sel ? "bg-fuchsia-500/10" : "hover:bg-white/[0.03]")}
                  >
                    <span className="w-8 font-mono text-[10.5px] text-ink-400">{e.seq}</span>
                    <KindIcon kind={e.kind} danger={e.destructive && !e.error} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[12.5px] text-ink-100">{e.name}</span>
                        <span className="font-mono text-[10px] text-ink-500">#{occurrence(e)}</span>
                        {e.destructive && <Badge tone="red">destructive</Badge>}
                        {e.error && <Badge tone="red">{e.error.type}</Badge>}
                      </div>
                      <div className="truncate font-mono text-[10.5px] text-ink-400">{describe(e)}</div>
                    </div>
                    {sel && <Badge tone="fuchsia">⚡ target</Badge>}
                  </li>
                );
              })}
            </ol>
          </Card>

          <div className="space-y-5">
            <Card title="2 · Choose the failure" subtitle={preset ? `Preset: ${sc?.fault_presets.find((p) => p.id === preset)?.summary ?? ""}` : target ? `Target: ${target.name} (occurrence #${occurrence(target)})` : "Select a step on the left or a preset above"}>
              <div className="space-y-3 p-4">
                <div className="flex flex-wrap gap-1.5">
                  {(kinds.data ?? []).map((k) => (
                    <button
                      key={k.id}
                      onClick={() => pickKind(k.id)}
                      className={cx("rounded-md px-2 py-1 text-[11.5px] ring-1 ring-inset", kind === k.id ? "bg-fuchsia-500/15 text-fuchsia-100 ring-fuchsia-400/40" : "text-ink-300 ring-white/10 hover:text-white")}
                    >
                      {k.title}
                    </button>
                  ))}
                </div>
                {kindDef && (
                  <div className="rounded-lg border hairline bg-ink-950/60 p-3 text-[12.5px] text-ink-200">
                    {kindDef.description}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone="fuchsia">strategy: {kindDef.strategy}</Badge>
                      {kindDef.requires_branch ? <Badge tone="violet">requires branch execution</Badge> : <Badge tone="cyan">replay-safe substitution</Badge>}
                    </div>
                  </div>
                )}
                <label className="block">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Parameters (JSON)</span>
                  <textarea
                    value={params}
                    onChange={(e) => { setParams(e.target.value); setPreset(undefined); }}
                    rows={4}
                    spellCheck={false}
                    className="mt-1 w-full rounded-lg border hairline bg-ink-950 p-2.5 font-mono text-[12px] text-ink-100 outline-none focus:border-fuchsia-400/50"
                  />
                </label>
                <Button variant="primary" onClick={() => void run()} disabled={running || (!target && !preset)}>
                  {running ? <><Spinner className="size-3.5" /> Running counterfactual…</> : "⚡ Inject failure and run"}
                </Button>
              </div>
            </Card>

            {error && <ErrorBox error={error} />}

            {result && resultEx && (
              <Card
                className="animate-rise"
                title={<span className="flex items-center gap-2">3 · Result <Verdict verdict={result.execution.invariants_failed ? "fail" : result.execution.status === "diverged" ? "diverged" : "pass"} /></span>}
                subtitle={resultEx.title || resultEx.id}
                actions={<ModeBadge mode={resultEx.mode} />}
              >
                <div className="space-y-4 p-4">
                  {injected && <FaultSummary event={injected} />}
                  {resultEx.divergence && (
                    <div className="rounded-lg border border-amber-400/25 bg-amber-400/[0.05] p-3 text-[12.5px] text-amber-100">
                      <Badge tone="amber">{resultEx.divergence.type}</Badge> {resultEx.divergence.message}
                    </div>
                  )}
                  {resultEx.status === "diverged" && (
                    <div className="rounded-lg border border-violet-400/25 bg-violet-500/[0.06] p-3 text-[12.5px] text-violet-100">
                      Strict offline replay stopped at the divergence: what the agent would do next is unknown without executing it.
                      <div className="mt-2"><Button variant="primary" onClick={() => void run("branch")}>Run as branch execution →</Button></div>
                    </div>
                  )}
                  <div className="overflow-hidden rounded-lg border hairline"><InvariantList invariants={resultEx.invariants} dense /></div>
                  {resultEx.output && <div className="text-[12.5px] text-ink-300">Agent said: <span className="text-ink-100">“{resultEx.output.message}”</span></div>}
                  <div className="flex flex-wrap gap-2">
                    <Button href={href({ name: "execution", lab, id: resultEx.id })}>Open timeline</Button>
                    <Button href={href({ name: "diff", lab, a: reference.id, b: resultEx.id })}>Diff vs recording</Button>
                    <Button href={href({ name: "regression", lab, id: resultEx.id })}>Make it a regression test →</Button>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
