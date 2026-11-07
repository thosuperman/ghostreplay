import { useEffect, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { DemoStep, DemoStory, Execution, GREvent, TraceDiff } from "../api/types";
import { FaultSummary } from "../components/FaultSummary";
import { InvariantList, Timeline } from "../components/execution";
import { Badge, Button, Card, cx, ErrorBox, Spinner, Verdict } from "../components/ui";
import { describe } from "../lib/format";
import { href } from "../lib/router";

interface Loaded {
  story: DemoStory;
  executions: Record<string, Execution>;
  fixDiff?: TraceDiff;
}

const cache = new Map<LabId, Loaded>();

const PREP_STEPS = [
  "Recording the incident against simulated backends",
  "Replaying it offline (tools and network blocked)",
  "Recording a healthy baseline",
  "Injecting the failure into the baseline",
  "Running the fixed agent against the same failure",
  "Generating and running regression cases",
];

export function Story({ lab }: { lab: LabId }) {
  const [loaded, setLoaded] = useState<Loaded | undefined>(cache.get(lab));
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);

  const run = async () => {
    setBusy(true);
    setError(undefined);
    setTick(0);
    const timer = window.setInterval(() => setTick((t) => Math.min(t + 1, PREP_STEPS.length - 1)), 260);
    try {
      const story = await api.demo(lab, LABS[lab].scenario);
      const ids = [...new Set(story.steps.flatMap((s) => s.execution_ids))];
      const execs = await Promise.all(ids.map((id) => api.execution(lab, id)));
      const executions = Object.fromEntries(execs.map((e) => [e.id, e]));
      const fix = story.steps.find((s) => s.id === "fix");
      const fixDiff = fix && fix.execution_ids.length === 2 ? await api.diff(lab, fix.execution_ids[0]!, fix.execution_ids[1]!) : undefined;
      const value = { story, executions, fixDiff };
      cache.set(lab, value);
      setLoaded(value);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      window.clearInterval(timer);
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!cache.get(lab)) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lab]);

  if (error) return <ErrorBox error={error} />;
  if (!loaded || busy) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">{LABS[lab].name}</div>
        <h1 className="mt-2 text-2xl font-semibold text-white">Preparing the demo with real executions…</h1>
        <ol className="mt-8 space-y-3">
          {PREP_STEPS.map((s, i) => (
            <li key={s} className={cx("flex items-center gap-3 text-sm transition-colors", i <= tick ? "text-ink-100" : "text-ink-500")}>
              {i < tick ? <span className="text-emerald-400">✓</span> : i === tick ? <Spinner className="size-3.5" /> : <span className="size-3.5" />}
              {s}
            </li>
          ))}
        </ol>
      </div>
    );
  }

  const { story, executions, fixDiff } = loaded;
  const reproduced = story.steps[0]?.verdict === "fail";
  const proven = story.steps.at(-1)?.verdict === "pass";
  return (
    <div className="animate-fade">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">Guided demo · {LABS[lab].name}</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white">{story.title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-300">
            An AI agent made a dangerous mistake. GhostReplay reproduced it, exposed the cause, and proved that the fix works. Every
            step below links to a real, stored execution.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-xl border hairline bg-ink-900 px-3 py-2 text-xs">
            <Badge tone={reproduced ? "green" : "red"}>{reproduced ? "✓" : "✕"} bug reproduced</Badge>
            <Badge tone={proven ? "green" : "red"}>{proven ? "✓" : "✕"} fix proven</Badge>
          </div>
          <Button onClick={() => void run()}>↻ Run again</Button>
        </div>
      </div>

      <ol className="relative space-y-6 before:absolute before:bottom-6 before:left-[15px] before:top-6 before:w-px before:bg-gradient-to-b before:from-violet-400/50 before:via-white/10 before:to-emerald-400/40">
        {story.steps.map((step, i) => (
          <li key={step.id} className="relative pl-12" style={{ animation: `rise 320ms ${i * 90}ms both` }}>
            <span
              className={cx(
                "absolute left-0 top-3 grid size-8 place-items-center rounded-full border font-mono text-xs font-semibold",
                step.verdict === "fail"
                  ? "border-rose-400/60 bg-rose-500/15 text-rose-200"
                  : step.verdict === "pass"
                    ? "border-emerald-400/60 bg-emerald-500/15 text-emerald-200"
                    : "border-violet-400/60 bg-violet-500/15 text-violet-200",
              )}
            >
              {i + 1}
            </span>
            <StepCard lab={lab} step={step} story={story} executions={executions} fixDiff={fixDiff} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function StepCard({ lab, step, story, executions, fixDiff }: {
  lab: LabId;
  step: DemoStep;
  story: DemoStory;
  executions: Record<string, Execution>;
  fixDiff?: TraceDiff;
}) {
  const ex = (i: number) => executions[step.execution_ids[i] ?? ""];
  return (
    <Card
      title={<span className="flex items-center gap-2.5 text-[15px]">{step.title.replace(/^\d+ · /, "")} <Verdict verdict={step.verdict} /></span>}
      subtitle={step.narrative}
    >
      <div className="p-4">
        {step.id === "incident" && ex(0) && <IncidentStep lab={lab} execution={ex(0)!} />}
        {step.id === "replay" && ex(0) && ex(1) && <ReplayStep lab={lab} original={ex(0)!} replay={ex(1)!} step={step} />}
        {step.id === "explain" && ex(0) && <ExplainStep execution={ex(0)!} headline={String(step.data.headline_invariant ?? "")} lab={lab} />}
        {step.id === "counterfactual" && ex(1) && <CounterfactualStep lab={lab} baseline={ex(0)} cf={ex(1)!} />}
        {step.id === "fix" && ex(0) && ex(1) && <FixStep lab={lab} vuln={ex(0)!} fixed={ex(1)!} diff={fixDiff} />}
        {step.id === "prove" && <ProveStep lab={lab} story={story} cfId={story.steps.find((s) => s.id === "counterfactual")?.execution_ids[1]} />}
      </div>
    </Card>
  );
}

function IncidentStep({ lab, execution }: { lab: LabId; execution: Execution }) {
  const failed = execution.invariants.filter((i) => i.status === "failed");
  const evidence = failed.flatMap((i) => i.evidence);
  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
      <div className="overflow-hidden rounded-lg border hairline">
        <Timeline execution={execution} highlight={evidence} compact />
      </div>
      <div className="space-y-3">
        <div className="overflow-hidden rounded-lg border border-rose-400/20">
          <InvariantList invariants={failed} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button href={href({ name: "execution", lab, id: execution.id })} variant="primary">Inspect the timeline →</Button>
          <Badge tone="blue">recorded run · {execution.provenance.model_provider} model · simulated backends</Badge>
        </div>
      </div>
    </div>
  );
}

function ReplayStep({ lab, original, replay, step }: { lab: LabId; original: Execution; replay: Execution; step: DemoStep }) {
  const interactions = replay.events.filter((e) => ["model_call", "tool_call", "nondeterminism"].includes(e.kind));
  const matched = interactions.filter((e) => e.replay?.verdict === "matched").length;
  const identical = step.data.identical === true;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="grid flex-1 grid-cols-2 gap-4 md:grid-cols-4">
        <Metric label="interactions served" value={`${matched}/${interactions.length}`} tone="cyan" />
        <Metric label="tool handlers invoked" value="0" tone="green" hint="replay uses a registry whose handlers raise if called" />
        <Metric label="network" value="blocked" tone="green" hint="socket connect/getaddrinfo raise on the replay thread" />
        <Metric label="diff vs recording" value={identical ? "identical" : `${String(step.data.diff_entries)} changes`} tone={identical ? "green" : "amber"} />
      </div>
      <div className="flex gap-2">
        <Button variant="primary" href={href({ name: "replay", lab, id: original.id })}>▶ Watch the replay engine</Button>
        <Button href={href({ name: "diff", lab, a: original.id, b: replay.id })}>Diff</Button>
      </div>
    </div>
  );
}

function Metric({ label, value, tone, hint }: { label: string; value: string; tone: "cyan" | "green" | "amber" | "red"; hint?: string }) {
  const color = { cyan: "text-cyan-300", green: "text-emerald-300", amber: "text-amber-300", red: "text-rose-300" }[tone];
  return (
    <div className="rounded-lg border hairline bg-ink-950/60 px-3 py-2.5" title={hint}>
      <div className="text-[10.5px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className={cx("mt-1 font-mono text-lg font-semibold", color)}>{value}</div>
    </div>
  );
}

function EvidenceEvent({ e }: { e: GREvent }) {
  return (
    <div className={cx("rounded-lg border p-3", e.error ? "border-rose-400/30 bg-rose-500/[0.05]" : "hairline bg-ink-950/60")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-ink-400">seq {e.seq}</span>
        <span className="font-mono text-[13px] font-semibold text-white">{e.name}</span>
        {e.destructive && <Badge tone="red">destructive</Badge>}
        {e.error ? <Badge tone="red">{e.error.type}</Badge> : <Badge tone="green">succeeded</Badge>}
      </div>
      <div className="mt-1.5 font-mono text-[11px] text-ink-300">{describe(e)}</div>
      {e.error && <div className="mt-1.5 text-[12px] text-rose-200">{e.error.message}</div>}
      {e.state_after !== null && (
        <div className="mt-2 text-[11px] text-ink-400">
          observable state after: <span className="font-mono text-ink-200">{JSON.stringify(e.state_after)}</span>
        </div>
      )}
    </div>
  );
}

function ExplainStep({ lab, execution, headline }: { lab: LabId; execution: Execution; headline: string }) {
  const inv = execution.invariants.find((i) => i.id === headline) ?? execution.invariants.find((i) => i.status === "failed");
  const evidence = (inv?.evidence ?? [])
    .map((id) => execution.events.find((e) => e.event_id === id))
    .filter((e): e is GREvent => e !== undefined);
  const steps = execution.events.filter((e) => e.kind === "agent_step");
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {evidence.map((e) => (
          <EvidenceEvent key={e.event_id} e={e} />
        ))}
      </div>
      {steps.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-300">
          agent-declared steps:
          {steps.map((s) => (
            <Badge key={s.event_id} tone="amber">↳ {s.name} {s.request && typeof s.request === "object" && !Array.isArray(s.request) && "idempotency_key" in s.request ? `(idempotency_key: ${JSON.stringify(s.request.idempotency_key)})` : ""}</Badge>
          ))}
        </div>
      )}
      <Button href={href({ name: "execution", lab, id: execution.id, focus: evidence[0]?.event_id })}>Open evidence in inspector →</Button>
    </div>
  );
}

function CounterfactualStep({ lab, baseline, cf }: { lab: LabId; baseline?: Execution; cf: Execution }) {
  const injected = cf.events.find((e) => e.fault);
  const failed = cf.invariants.filter((i) => i.status === "failed");
  return (
    <div className="space-y-4">
      {injected && <FaultSummary event={injected} />}
      <div className="overflow-hidden rounded-lg border border-rose-400/20">
        <InvariantList invariants={failed} dense />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" href={href({ name: "failure-lab", lab, id: baseline?.id })}>Open the Failure Lab →</Button>
        <Button href={href({ name: "execution", lab, id: cf.id })}>Counterfactual timeline</Button>
        <Badge tone="violet" title="Prefix replayed from the recording, then re-executed against a fresh simulated environment">branch execution · labelled</Badge>
      </div>
    </div>
  );
}

function FixStep({ lab, vuln, fixed, diff }: { lab: LabId; vuln: Execution; fixed: Execution; diff?: TraceDiff }) {
  return (
    <div className="space-y-4">
      {diff?.first_divergence && (
        <div className="rounded-lg border border-amber-400/25 bg-amber-400/[0.05] px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">First divergence between vulnerable and fixed</div>
          <div className="mt-1 font-mono text-[13px] text-amber-100">{diff.first_divergence.summary}</div>
        </div>
      )}
      {diff && (
        <div className="overflow-hidden rounded-lg border hairline">
          <table className="w-full text-[12.5px]">
            <thead className="bg-white/[0.02] text-[11px] uppercase tracking-wider text-ink-400">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Invariant</th>
                <th className="px-3 py-2 text-left font-medium">Vulnerable</th>
                <th className="px-3 py-2 text-left font-medium">Fixed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06]">
              {diff.behavior.invariants.map((i) => (
                <tr key={i.id}>
                  <td className="px-3 py-2 font-mono text-ink-200">{i.id}</td>
                  <td className="px-3 py-2">{i.a && <Verdict verdict={i.a === "passed" ? "pass" : i.a === "failed" ? "fail" : "inconclusive"} />}</td>
                  <td className="px-3 py-2">{i.b && <Verdict verdict={i.b === "passed" ? "pass" : i.b === "failed" ? "fail" : "inconclusive"} />}</td>
                </tr>
              ))}
              <tr>
                <td className="px-3 py-2 text-ink-300">destructive side effects committed</td>
                <td className="px-3 py-2 font-mono text-rose-300">{diff.behavior.destructive_calls[0]}</td>
                <td className="px-3 py-2 font-mono text-emerald-300">{diff.behavior.destructive_calls[1]}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Quote label="Vulnerable agent told the user" text={vuln.output?.message} tone="red" />
        <Quote label="Fixed agent told the user" text={fixed.output?.message} tone="green" />
      </div>
      <Button variant="primary" href={href({ name: "diff", lab, a: vuln.id, b: fixed.id })}>Open side-by-side diff →</Button>
    </div>
  );
}

function Quote({ label, text, tone }: { label: string; text?: string; tone: "red" | "green" }) {
  return (
    <div className={cx("rounded-lg border p-3", tone === "red" ? "border-rose-400/20 bg-rose-500/[0.04]" : "border-emerald-400/20 bg-emerald-500/[0.04]")}>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{label}</div>
      <div className="mt-1 text-[13px] leading-relaxed text-ink-100">“{text ?? "—"}”</div>
    </div>
  );
}

function ProveStep({ lab, story, cfId }: { lab: LabId; story: DemoStory; cfId?: string }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {story.reports.map((r) => (
          <div key={r.case_id} className={cx("rounded-lg border p-3", r.passed ? "border-emerald-400/25" : "border-rose-400/25")}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[12px] text-ink-200">{r.case_id}</span>
              <Verdict verdict={r.passed ? "pass" : "fail"} size="lg" />
            </div>
            <div className="mt-1.5 text-[12px] text-ink-300">
              agent variant <span className="font-mono text-ink-100">{r.variant}</span> · expected {r.expect.toUpperCase()} ·{" "}
              {r.outcome_matches_expectation ? <span className="text-emerald-300">detector works as intended</span> : <span className="text-rose-300">unexpected</span>}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {r.invariants.map((i) => (
                <Badge key={i.id} tone={i.status === "passed" ? "green" : i.status === "failed" ? "red" : "amber"}>
                  {i.status === "passed" ? "✓" : i.status === "failed" ? "✕" : "?"} {i.id}
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" href={href({ name: "regression", lab, id: cfId })}>Export the pytest regression →</Button>
        <code className="rounded-md bg-ink-950 px-2 py-1 font-mono text-[11.5px] text-ink-300">uv run pytest tests/regression</code>
      </div>
    </div>
  );
}
