import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, LABS } from "../api/client";
import type { Execution, GREvent, RegressionReport, Scenario, TraceDiff } from "../api/types";
import { Inspector, Timeline } from "../components/execution";
import { Badge, Button, cx, ErrorBox, Spinner } from "../components/ui";
import { href, type DemoId } from "../lib/router";
import { countBySource, DEMOS, reportFor, type CompareRow, type Fact, type StoryLine } from "./guided/demos";

const REPO = "https://github.com/thosuperman/ghost-replay";


interface State {
  buggy?: Execution;
  replay?: Execution;
  replayDiff?: TraceDiff;
  fixed?: Execution;
  compareDiff?: TraceDiff;
  reports?: RegressionReport[];
}

const STEP_TITLES = ["Meet the agent", "Watch the failure", "Investigate", "Replay safely", "Test the fix", "Verify the fix"];

export function GuidedDemo({ demo }: { demo: DemoId }) {
  const cfg = DEMOS[demo];
  const lab = cfg.lab;
  const [scenario, setScenario] = useState<Scenario>();
  const [state, setState] = useState<State>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string>();
  const stepRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    api.scenarios(lab).then((s) => setScenario(s.find((x) => x.id === cfg.scenario) ?? s[0]), (e) => setError(String(e?.message ?? e)));
  }, [lab, cfg.scenario]);

  const vulnerable = scenario?.variants.find((v) => !v.is_fix)?.id ?? "vulnerable";
  const fixedVariant = scenario?.variants.find((v) => v.is_fix)?.id ?? "fixed";
  const incident = useMemo(() => Object.fromEntries((scenario?.conditions ?? []).map((c) => [c.id, c.incident])), [scenario]);

  // How far the visitor has got: each step unlocks the next.
  const reached =
    state.reports ? 6 : state.fixed ? 5 : state.replay ? 4 : state.buggy ? 3 : 1;

  const go = async (step: number, action: () => Promise<Partial<State>>) => {
    setBusy(step);
    setError(undefined);
    try {
      const patch = await action();
      setState((s) => ({ ...s, ...patch }));
      setTimeout(() => stepRefs.current[step]?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const runAgent = () =>
    go(1, async () => {
      const s = await api.record(lab, cfg.scenario, vulnerable, incident, `Guided demo: ${cfg.title} (buggy agent)`);
      return { buggy: await api.execution(lab, s.id), replay: undefined, replayDiff: undefined, fixed: undefined, compareDiff: undefined, reports: undefined };
    });
  const replay = () =>
    go(3, async () => {
      const r = await api.replay(lab, state.buggy!.id);
      return { replay: await api.execution(lab, r.execution.id), replayDiff: r.diff };
    });
  const testFix = () =>
    go(4, async () => {
      const s = await api.record(lab, cfg.scenario, fixedVariant, incident, `Guided demo: ${cfg.title} (fixed agent)`);
      const [fixed, compareDiff] = await Promise.all([api.execution(lab, s.id), api.diff(lab, state.buggy!.id, s.id)]);
      return { fixed, compareDiff };
    });
  const verify = () => go(5, async () => ({ reports: await api.runRegression(lab, state.buggy!.id) }));

  const story = useMemo(() => (state.buggy ? cfg.story(state.buggy) : []), [state.buggy, cfg]);

  return (
    <div className="animate-fade mx-auto max-w-4xl" data-testid="guided-demo" data-demo={demo}>
      <header className="mb-8">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">{cfg.eyebrow}</div>
        <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">{cfg.title}</h1>
        <p className="mt-3 text-lg leading-relaxed text-ink-300">{cfg.subtitle}</p>
        <ol className="mt-6 flex flex-wrap gap-2" aria-label="Progress">
          {STEP_TITLES.map((t, i) => (
            <li
              key={t}
              className={cx(
                "flex items-center gap-2 rounded-full px-3 py-1 text-xs ring-1 ring-inset",
                i + 1 < reached || (i + 1 === 6 && state.reports)
                  ? "bg-emerald-400/10 text-emerald-200 ring-emerald-400/30"
                  : i + 1 === reached
                    ? "bg-violet-500/15 text-violet-100 ring-violet-400/40"
                    : "text-ink-400 ring-white/10",
              )}
            >
              <span className="font-mono">{i + 1}</span> {t}
            </li>
          ))}
        </ol>
      </header>

      {error && (
        <div className="mb-6" role="alert">
          <ErrorBox error={error} />
        </div>
      )}

      {/* 1 — Meet the agent */}
      <Step n={1} title="Meet the agent" refCb={(el) => (stepRefs.current[0] = el)}>
        <div className="space-y-3">
          {cfg.conversation.map((m) => (
            <div key={m.text} className={cx("flex", m.role === "agent" ? "justify-end" : "justify-start")}>
              <div
                className={cx(
                  "max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed",
                  m.role === "agent" ? "bg-violet-500/15 text-violet-50 ring-1 ring-violet-400/25" : m.role === "system" ? "bg-amber-400/10 text-amber-100 ring-1 ring-amber-400/25" : "bg-white/[0.06] text-ink-100 ring-1 ring-white/10",
                )}
              >
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider opacity-70">{m.who}</div>
                {m.text}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-5 text-[15px] leading-relaxed text-ink-200">{cfg.agentExplainer}</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {cfg.tools.map((t) => (
            <div key={t.name} className="rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/10">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                {t.label}
                {t.danger && <Badge tone="red">takes action</Badge>}
              </div>
              <div className="mt-0.5 text-[13px] text-ink-300">{t.what}</div>
              <div className="mt-1 font-mono text-[11px] text-ink-400">{t.name}</div>
            </div>
          ))}
        </div>
        <Cta onClick={runAgent} busy={busy === 1} disabled={!scenario} label={state.buggy ? "Run the agent again" : cfg.runCta} testId="run-agent" />
        <Honesty>
          Scripted agent: the decisions come from a deterministic policy, not a live LLM, so the demo is reproducible and free. The run happens now, on this server, against simulated services.
        </Honesty>
      </Step>

      {/* 2 — Watch the failure */}
      {state.buggy && (
        <Step n={2} title="Watch the failure" tone="bad" refCb={(el) => (stepRefs.current[1] = el)}>
          <p className="text-xl font-semibold text-rose-200" data-testid="failure-headline">{cfg.failureHeadline(state.buggy)}</p>
          <Facts facts={cfg.failureFacts(state.buggy)} />
          <h3 className="mt-6 text-sm font-semibold uppercase tracking-wider text-ink-400">What happened, step by step</h3>
          <ol className="mt-3 space-y-2" data-testid="failure-story">
            {story.filter((l) => l.key).map((l, i) => (
              <StoryItem key={l.eventId} line={l} n={i + 1} />
            ))}
          </ol>
          <p className="mt-5 rounded-xl bg-rose-500/[0.07] px-4 py-3 text-[15px] leading-relaxed text-rose-100 ring-1 ring-rose-400/20">{cfg.failureExplain}</p>
          <SourceNote ex={state.buggy} lab={lab} />
        </Step>
      )}

      {/* 3 — Investigate */}
      {state.buggy && (
        <Step n={3} title="Investigate the failure" refCb={(el) => (stepRefs.current[2] = el)}>
          <p className="text-[15px] leading-relaxed text-ink-200">
            GhostReplay recorded every decision and tool call in order. Here is the full run in plain English. The highlighted lines are the ones that matter.
          </p>
          <ol className="mt-4 space-y-1.5">
            {story.map((l, i) => (
              <StoryItem key={l.eventId} line={l} n={i + 1} compact />
            ))}
          </ol>
          <h3 className="mt-6 text-sm font-semibold text-white">Why the retry was unsafe</h3>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-200">{cfg.whyUnsafe}</p>
          <TechDetails ex={state.buggy} highlight={story.filter((l) => l.key && l.tone === "bad").map((l) => l.eventId)} />
          <Cta onClick={replay} busy={busy === 3} label={state.replay ? "Replay again" : "Replay the Failure"} testId="replay" />
        </Step>
      )}

      {/* 4 — Replay safely */}
      {state.replay && state.buggy && (
        <Step n={4} title="Replay safely" tone="info" refCb={(el) => (stepRefs.current[3] = el)}>
          <p className="text-[15px] leading-relaxed text-ink-200">
            GhostReplay reuses recorded model and tool responses, so developers can reproduce the observed execution without calling the real {demo === "refund" ? "payment service" : "cloud API"} again.
          </p>
          <ReplayFacts replay={state.replay} diff={state.replayDiff} />
          {state.replay.divergence && (
            <p className="mt-4 rounded-xl bg-amber-400/10 px-4 py-3 text-sm text-amber-100 ring-1 ring-amber-400/25" role="status">
              The replay diverged: {state.replay.divergence.message}
            </p>
          )}
          <Honesty>Strict offline replay: tool handlers are replaced by stubs that throw if called, so nothing can reach a backend.</Honesty>
          <DevLink href={href({ name: "replay", lab, id: state.buggy.id })}>Watch it stream in Replay Studio</DevLink>
          <Cta onClick={testFix} busy={busy === 4} label={state.fixed ? "Run the fixed agent again" : "Test the Fix"} testId="test-fix" />
        </Step>
      )}

      {/* 5 — Compare */}
      {state.fixed && state.buggy && (
        <Step n={5} title="Compare the buggy and fixed agents" tone="good" refCb={(el) => (stepRefs.current[4] = el)}>
          <h3 className="text-lg font-semibold text-white">{cfg.fixTitle}</h3>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-200">{cfg.fixText}</p>
          <CompareTable rows={cfg.compare(state.buggy, state.fixed)} />
          <h3 className="mt-6 text-sm font-semibold uppercase tracking-wider text-ink-400">What the fixed agent did differently</h3>
          <ol className="mt-3 space-y-2" data-testid="fixed-story">
            {cfg.story(state.fixed).filter((l) => l.key).map((l, i) => (
              <StoryItem key={l.eventId} line={l} n={i + 1} />
            ))}
          </ol>
          {state.compareDiff?.first_divergence && (
            <p className="mt-4 text-[15px] text-ink-200">
              <span className="font-semibold text-white">Where the two runs first differ: </span>
              <span className="font-mono text-cyan-200">{state.compareDiff.first_divergence.summary}</span>
              {" "}({state.compareDiff.entries.length} structural difference{state.compareDiff.entries.length === 1 ? "" : "s"} in total).
            </p>
          )}
          <Honesty>Re-executed simulation: the fixed agent ran from scratch against fresh simulated services with the same failure condition. This is not a replay, because the code changed.</Honesty>
          <DevLink href={href({ name: "diff", lab, a: state.buggy.id, b: state.fixed.id })}>Open the full structural diff</DevLink>
          <Cta onClick={verify} busy={busy === 5} label={state.reports ? "Run the regression tests again" : "Verify the Fix"} testId="verify" />
        </Step>
      )}

      {/* 6 — Verify */}
      {state.reports && state.buggy && (
        <Step n={6} title="Regression verification" tone="good" refCb={(el) => (stepRefs.current[5] = el)}>
          <Verification reports={state.reports} vulnerable={vulnerable} fixed={fixedVariant} headline={cfg.headlineInvariant} before={cfg.verifyBefore} after={cfg.verifyAfter} />
          <p className="mt-5 text-[15px] leading-relaxed text-ink-200">
            GhostReplay converts failures into repeatable tests so developers can prevent the same bug from returning. Both tests just ran on this server: the same failure scenario, once per agent.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button href={href({ name: "execution", lab, id: state.buggy.id })}>Explore Full Execution</Button>
            <Button href={href({ name: "regression", lab, id: state.buggy.id })}>Export Regression Test</Button>
            <Button href={href({ name: "demo", demo: cfg.otherDemo })}>Try {cfg.otherDemo === "devops" ? "DevOps" : "Refund"} Demo</Button>
            <Button variant="primary" href={href({ name: "connect" })}>Connect Your Own Agent</Button>
            <Button variant="ghost" href={`${REPO}/tree/main/${cfg.sourcePath}`}>View Source Code ↗</Button>
          </div>
        </Step>
      )}
    </div>
  );
}

// -- building blocks --------------------------------------------------------------------------

function Step({ n, title, children, tone = "neutral", refCb }: { n: number; title: string; children: ReactNode; tone?: "neutral" | "bad" | "good" | "info"; refCb: (el: HTMLElement | null) => void }) {
  const ring = { neutral: "ring-white/10", bad: "ring-rose-400/25", good: "ring-emerald-400/25", info: "ring-cyan-400/25" }[tone];
  const dot = { neutral: "bg-violet-500/80", bad: "bg-rose-500/80", good: "bg-emerald-500/80", info: "bg-cyan-500/80" }[tone];
  return (
    <section ref={refCb} className={cx("animate-fade mb-6 scroll-mt-24 rounded-2xl bg-ink-900/80 p-5 ring-1 sm:p-7", ring)} data-testid={`step-${n}`} aria-labelledby={`step-${n}-title`}>
      <div className="mb-4 flex items-center gap-3">
        <span className={cx("grid size-7 place-items-center rounded-full font-mono text-sm font-semibold text-white", dot)}>{n}</span>
        <h2 id={`step-${n}-title`} className="text-xl font-semibold text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Cta({ onClick, busy, disabled, label, testId }: { onClick: () => void; busy: boolean; disabled?: boolean; label: string; testId: string }) {
  return (
    <div className="mt-6">
      <button
        type="button"
        onClick={onClick}
        disabled={busy || disabled}
        data-testid={testId}
        className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-violet-500 to-violet-600 px-5 py-2.5 text-[15px] font-semibold text-white shadow-[0_0_0_1px_rgb(167_139_250/0.5),0_10px_30px_-10px_rgb(139_92_246/0.8)] transition-colors hover:from-violet-400 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? <Spinner /> : null}
        {busy ? "Running…" : `${label} →`}
      </button>
    </div>
  );
}

function Honesty({ children }: { children: ReactNode }) {
  return <p className="mt-4 text-xs leading-relaxed text-ink-400">{children}</p>;
}

function DevLink({ href: to, children }: { href: string; children: ReactNode }) {
  return (
    <a href={to} className="mt-3 inline-block text-sm text-cyan-300 underline-offset-4 hover:underline">
      Developer mode: {children} →
    </a>
  );
}

function Facts({ facts }: { facts: Fact[] }) {
  const color = { red: "text-rose-300", green: "text-emerald-300", amber: "text-amber-300", cyan: "text-cyan-300" };
  return (
    <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="facts">
      {facts.map((f) => (
        <div key={f.label} className="rounded-xl bg-white/[0.03] px-4 py-3 ring-1 ring-white/10">
          <dt className="text-[11px] font-medium uppercase tracking-wider text-ink-400">{f.label}</dt>
          <dd className={cx("mt-1 font-mono text-xl font-semibold", f.tone ? color[f.tone] : "text-white")}>{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function StoryItem({ line, n, compact }: { line: StoryLine; n: number; compact?: boolean }) {
  const tone = {
    bad: "bg-rose-500/[0.08] text-rose-100 ring-rose-400/25",
    warn: "bg-amber-400/[0.08] text-amber-100 ring-amber-400/25",
    good: "bg-emerald-500/[0.08] text-emerald-100 ring-emerald-400/25",
    neutral: "bg-white/[0.02] text-ink-200 ring-white/10",
  }[line.tone];
  return (
    <li className={cx("flex gap-3 rounded-xl px-4 ring-1", compact ? "py-2 text-sm" : "py-3 text-[15px]", tone, compact && !line.key && "opacity-80")}>
      <span className="font-mono text-xs leading-6 opacity-60">{n}.</span>
      <span className="leading-relaxed">{line.text}</span>
      <span className="ml-auto shrink-0 font-mono text-[10.5px] leading-6 opacity-50">seq {line.seq}</span>
    </li>
  );
}

function TechDetails({ ex, highlight }: { ex: Execution; highlight: string[] }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<GREvent>();
  return (
    <div className="mt-6">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-sm font-medium text-cyan-300 hover:text-cyan-200" data-testid="tech-details">
        {open ? "▾ Hide technical details" : "▸ Show technical details (model decisions, tool arguments, responses, state, errors, timestamps)"}
      </button>
      {open && (
        <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="rounded-xl ring-1 ring-white/10">
            <Timeline execution={ex} selected={selected?.event_id} onSelect={setSelected} highlight={highlight} compact />
          </div>
          <div className="rounded-xl ring-1 ring-white/10">
            {selected ? <Inspector event={selected} /> : <p className="p-4 text-sm text-ink-300">Select an event to inspect its request, response, state change and timing.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function ReplayFacts({ replay, diff }: { replay: Execution; diff?: TraceDiff }) {
  const c = countBySource(replay);
  const facts: Fact[] = [
    { label: "Recorded responses reused", value: String(c.recorded), tone: "cyan" },
    { label: "External tool executions", value: String(c.toolsExecuted), tone: c.toolsExecuted === 0 ? "green" : "red" },
    { label: "Divergence", value: replay.divergence ? "Yes" : "None", tone: replay.divergence ? "amber" : "green" },
    { label: "Replay result", value: diff?.identical ? "Identical" : replay.status === "completed" ? "Different" : replay.status, tone: diff?.identical ? "green" : "amber" },
  ];
  return (
    <div data-testid="replay-facts">
      <Facts facts={facts} />
      <p className="mt-3 text-sm text-ink-300">
        {c.recorded} of {c.total} model and tool calls were answered from the recording; {c.live} were executed. The replayed run reaches the same verdicts:{" "}
        {replay.invariants.filter((i) => i.status === "failed").map((i) => i.id).join(", ") || "no invariant failed"}.
      </p>
    </div>
  );
}

function CompareTable({ rows }: { rows: CompareRow[] }) {
  return (
    <div className="mt-5 overflow-x-auto rounded-xl ring-1 ring-white/10">
      <table className="w-full text-left text-[15px]" data-testid="compare-table">
        <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wider text-ink-400">
          <tr>
            <th className="px-4 py-2.5 font-medium">Metric</th>
            <th className="px-4 py-2.5 font-medium">Buggy agent</th>
            <th className="px-4 py-2.5 font-medium">Fixed agent</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-white/5">
              <td className="px-4 py-2.5 text-ink-200">{r.label}</td>
              <td className={cx("px-4 py-2.5 font-mono", r.improved ? "text-rose-300" : "text-ink-100")}>{r.buggy}</td>
              <td className={cx("px-4 py-2.5 font-mono", r.improved ? "text-emerald-300" : "text-ink-100")}>{r.fixed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Verification({ reports, vulnerable, fixed, headline, before, after }: { reports: RegressionReport[]; vulnerable: string; fixed: string; headline: string; before: string; after: string }) {
  const b = reportFor(reports, vulnerable);
  const a = reportFor(reports, fixed);
  const card = (r: RegressionReport | undefined, label: string, text: string) => {
    if (!r) return <div className="rounded-xl p-4 ring-1 ring-white/10">No report for {label}.</div>;
    const inv = r.invariants.find((i) => i.id === headline);
    const ok = r.passed;
    return (
      <div className={cx("rounded-xl p-5 ring-1", ok ? "bg-emerald-500/[0.07] ring-emerald-400/30" : "bg-rose-500/[0.07] ring-rose-400/30")} data-testid={`verify-${label.toLowerCase()}`} data-passed={ok}>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{label} · {r.variant} agent</div>
        <div className={cx("mt-1 text-2xl font-bold", ok ? "text-emerald-300" : "text-rose-300")}>{ok ? "PASSED" : "FAILED"}</div>
        <p className="mt-2 text-[15px] text-ink-100">{ok === (label === "After") ? text : "Unexpected result: see the report below."}</p>
        {inv && <p className="mt-2 font-mono text-xs text-ink-300">{inv.id}: {inv.message}</p>}
        <p className="mt-1 text-xs text-ink-400">expected {r.expect.toUpperCase()} · {r.outcome_matches_expectation ? "as expected" : "NOT as expected"} · execution {r.execution_id}</p>
      </div>
    );
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {card(b, "Before", before)}
      {card(a, "After", after)}
    </div>
  );
}

function SourceNote({ ex, lab }: { ex: Execution; lab: "support" | "devops" }) {
  return (
    <p className="mt-4 text-xs text-ink-400">
      Recorded execution <a className="font-mono text-cyan-300 hover:underline" href={href({ name: "execution", lab, id: ex.id })}>{ex.id}</a> · {ex.events.length} events · {LABS[lab].name} · model: {ex.provenance.label}
    </p>
  );
}
