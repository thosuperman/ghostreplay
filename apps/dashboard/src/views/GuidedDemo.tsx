import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Execution, GREvent, Library, RegressionReport, TraceDiff } from "../api/types";
import { ExecTypeBadges } from "../components/ExecTypeBadges";
import { Inspector, Timeline } from "../components/execution";
import { Badge, Button, cx, ErrorBox, Spinner } from "../components/ui";
import { href, type DemoId } from "../lib/router";
import { DEMOS, replayEvidence, type Actor, type CaptureIds, type CompareRow, type Fact, type StoryLine } from "./guided/demos";

const REPO = "https://github.com/thosuperman/ghostreplay";
const STEP_TITLES = ["Meet the agent", "Watch the failure", "Investigate", "Replay safely", "Test the fix", "Verify the fix"];

interface State {
  natural?: Execution;
  buggy?: Execution;
  replay?: Execution;
  replayDiff?: TraceDiff;
  fixed?: Execution;
  compareDiff?: TraceDiff;
  reports?: RegressionReport[];
}

export function GuidedDemo({ demo }: { demo: DemoId }) {
  const cfg = DEMOS[demo];
  const lab = cfg.lab;
  const [library, setLibrary] = useState<Library>();
  const [state, setState] = useState<State>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  const refs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    api.library(lab).then(setLibrary, (e) => setError(String(e?.message ?? e)));
  }, [lab]);
  const ids: CaptureIds | null = useMemo(() => (library ? cfg.pick(library.captures) : null), [library, cfg]);
  const capturedWith = library?.manifest.model ? `${library.manifest.model} (${library.manifest.provider})` : "a live model";
  const capturedOn = library?.manifest.captured ?? "";

  const go = async (key: string, scrollTo: string, action: () => Promise<Partial<State>>) => {
    setBusy(key);
    setError(undefined);
    try {
      const patch = await action();
      setState((s) => ({ ...s, ...patch }));
      setTimeout(() => refs.current[scrollTo]?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const rerun = async (captureId: string, title: string) => {
    const r = await api.reexecute(lab, captureId, title);
    return api.execution(lab, r.execution.id);
  };

  const reset = { buggy: undefined, replay: undefined, replayDiff: undefined, fixed: undefined, compareDiff: undefined, reports: undefined };
  const runAgent = () =>
    go("run", cfg.natural ? "natural" : "failure", async () =>
      cfg.natural
        ? { ...reset, natural: await rerun(ids!.natural!, `Guided demo: ${cfg.title} (workflow v1)`) }
        : { ...reset, buggy: await rerun(ids!.buggy, `Guided demo: ${cfg.title} (buggy agent)`) },
    );
  const inject = () => go("inject", "failure", async () => ({ ...reset, buggy: await rerun(ids!.buggy, `Guided demo: ${cfg.title} (injected decision, v1)`) }));
  const replay = () =>
    go("replay", "replay", async () => {
      const r = await api.replay(lab, state.buggy!.id);
      return { replay: await api.execution(lab, r.execution.id), replayDiff: r.diff };
    });
  const testFix = () =>
    go("fix", "fix", async () => {
      const fixed = await rerun(ids!.fixed, `Guided demo: ${cfg.title} (corrected)`);
      return { fixed, compareDiff: await api.diff(lab, state.buggy!.id, fixed.id) };
    });
  const verify = () =>
    go("verify", "verify", async () => {
      const [before, after] = await Promise.all([
        api.runRegressionFor(lab, ids!.buggy, ["vulnerable"]),
        api.runRegressionFor(lab, ids!.fixed, ["fixed"]),
      ]);
      return { reports: [...before, ...after] };
    });

  const story = useMemo(() => (state.buggy ? cfg.story(state.buggy) : []), [state.buggy, cfg]);
  const reached = state.reports ? 7 : state.fixed ? 6 : state.replay ? 5 : state.buggy ? 4 : 1;
  const ref = (k: string) => (el: HTMLElement | null) => {
    refs.current[k] = el;
  };

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
                i + 1 < reached ? "bg-emerald-400/10 text-emerald-200 ring-emerald-400/30" : i + 1 === reached ? "bg-violet-500/15 text-violet-100 ring-violet-400/40" : "text-ink-400 ring-white/10",
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
      {library && !ids && <div className="mb-6"><ErrorBox error="This server has no genuine captures for this demo." /></div>}

      <Step n={1} title="Meet the agent" refCb={ref("meet")}>
        <div className="space-y-3">
          {cfg.conversation.map((m) => (
            <div key={m.text} className={cx("flex", m.role === "agent" ? "justify-end" : "justify-start")}>
              <div className={cx("max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed", m.role === "agent" ? "bg-violet-500/15 text-violet-50 ring-1 ring-violet-400/25" : m.role === "system" ? "bg-amber-400/10 text-amber-100 ring-1 ring-amber-400/25" : "bg-white/[0.06] text-ink-100 ring-1 ring-white/10")}>
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
        <div className="mt-5 rounded-xl bg-cyan-400/[0.06] px-4 py-3 text-sm leading-relaxed text-cyan-50 ring-1 ring-cyan-400/20" data-testid="what-is-real">
          {cfg.realExplainer}
        </div>
        <Cta onClick={runAgent} busy={busy === "run"} disabled={!ids} label={state.buggy || state.natural ? "Run it again" : cfg.runCta} testId="run-agent" />
        <Honesty>
          The model's decisions come from a genuine live run of {capturedWith}{capturedOn ? ` recorded on ${capturedOn}` : ""}. This public server makes no paid model calls. Clicking re-executes that run now, for real: the same agent code, real HTTP requests and real SQL writes on this server, with Claude's recorded decisions.
        </Honesty>
      </Step>

      {cfg.natural && state.natural && (
        <Step n="2a" title={cfg.natural.title} tone="info" refCb={ref("natural")}>
          <div className="mb-3"><ExecTypeBadges e={state.natural} /></div>
          <p className="text-[15px] leading-relaxed text-ink-100" data-testid="natural-summary">{cfg.natural.summary(state.natural)}</p>
          <ol className="mt-4 space-y-1.5">{cfg.story(state.natural).map((l, i) => <StoryItem key={l.eventId} line={l} n={i + 1} compact />)}</ol>
          <p className="mt-5 rounded-xl bg-amber-400/[0.07] px-4 py-3 text-[15px] leading-relaxed text-amber-50 ring-1 ring-amber-400/20">{cfg.natural.explain}</p>
          <Cta onClick={inject} busy={busy === "inject"} label={state.buggy ? "Inject it again" : cfg.natural.injectCta} testId="inject" />
          <Honesty>{cfg.natural.injectExplain}</Honesty>
        </Step>
      )}

      {state.buggy && (
        <Step n={cfg.natural ? "2b" : 2} title="Watch the failure" tone="bad" refCb={ref("failure")}>
          <div className="mb-3"><ExecTypeBadges e={state.buggy} /></div>
          <p className="text-xl font-semibold text-rose-200" data-testid="failure-headline">{cfg.failureHeadline(state.buggy)}</p>
          <Facts facts={cfg.failureFacts(state.buggy)} />
          <h3 className="mt-6 text-sm font-semibold uppercase tracking-wider text-ink-400">What happened, and who did it</h3>
          <ol className="mt-3 space-y-2" data-testid="failure-story">
            {story.filter((l) => l.key).map((l, i) => <StoryItem key={l.eventId} line={l} n={i + 1} />)}
          </ol>
          <p className="mt-5 rounded-xl bg-rose-500/[0.07] px-4 py-3 text-[15px] leading-relaxed text-rose-100 ring-1 ring-rose-400/20">{cfg.failureExplain}</p>
          <SourceNote ex={state.buggy} lab={lab} />
        </Step>
      )}

      {state.buggy && (
        <Step n={3} title="Investigate the failure" refCb={ref("investigate")}>
          <p className="text-[15px] leading-relaxed text-ink-200">Every model decision and tool call was recorded in order. Here is the full run in plain English, with who did each step.</p>
          <ol className="mt-4 space-y-1.5" data-testid="full-story">{story.map((l, i) => <StoryItem key={l.eventId} line={l} n={i + 1} compact />)}</ol>
          <h3 className="mt-6 text-sm font-semibold text-white">Why it was unsafe</h3>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-200">{cfg.whyUnsafe}</p>
          <TechDetails ex={state.buggy} highlight={story.filter((l) => l.key && l.tone === "bad").map((l) => l.eventId)} />
          <Cta onClick={replay} busy={busy === "replay"} label={state.replay ? "Replay again" : "Replay the Failure"} testId="replay" />
        </Step>
      )}

      {state.replay && state.buggy && (
        <Step n={4} title="Replay safely" tone="info" refCb={ref("replay")}>
          <div className="mb-3"><ExecTypeBadges e={state.replay} /></div>
          <p className="text-[15px] leading-relaxed text-ink-200">
            GhostReplay ran the same agent code again, offline. Every model and tool response was served from the recording, so neither {state.buggy.provenance.model_provider === "scripted" ? "the model" : "Claude"} nor the {demo === "refund" ? "refund service or the database" : "lab"} was contacted.
          </p>
          <ReplayFacts replay={state.replay} diff={state.replayDiff} />
          {state.replay.divergence && <p className="mt-4 rounded-xl bg-amber-400/10 px-4 py-3 text-sm text-amber-100 ring-1 ring-amber-400/25" role="status">The replay diverged: {state.replay.divergence.message}</p>}
          <Honesty>Strict offline replay: no world is created, tool handlers are stubs that throw if reached, and network access is blocked on the replaying thread. A replay reproduces the recording; it is not a re-run of changed code.</Honesty>
          <DevLink href={href({ name: "replay", lab, id: state.buggy.id })}>Watch it stream in Replay Studio</DevLink>
          <Cta onClick={testFix} busy={busy === "fix"} label={state.fixed ? "Run the fix again" : "Test the Fix"} testId="test-fix" />
        </Step>
      )}

      {state.fixed && state.buggy && (
        <Step n={5} title="Compare the buggy and fixed versions" tone="good" refCb={ref("fix")}>
          <div className="mb-3"><ExecTypeBadges e={state.fixed} /></div>
          <h3 className="text-lg font-semibold text-white">{cfg.fixTitle}</h3>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-200">{cfg.fixText}</p>
          <CompareTable rows={cfg.compare(state.buggy, state.fixed)} />
          <h3 className="mt-6 text-sm font-semibold uppercase tracking-wider text-ink-400">What the fixed version did differently</h3>
          <ol className="mt-3 space-y-2" data-testid="fixed-story">{cfg.story(state.fixed).filter((l) => l.key).map((l, i) => <StoryItem key={l.eventId} line={l} n={i + 1} />)}</ol>
          {state.compareDiff?.first_divergence && (
            <p className="mt-4 text-[15px] text-ink-200">
              <span className="font-semibold text-white">Where the two runs first differ: </span>
              <span className="font-mono text-cyan-200">{state.compareDiff.first_divergence.summary}</span> ({state.compareDiff.entries.length} structural difference{state.compareDiff.entries.length === 1 ? "" : "s"}).
            </p>
          )}
          <DevLink href={href({ name: "diff", lab, a: state.buggy.id, b: state.fixed.id })}>Open the full structural diff</DevLink>
          <Cta onClick={verify} busy={busy === "verify"} label={state.reports ? "Run the regression tests again" : "Verify the Fix"} testId="verify" />
        </Step>
      )}

      {state.reports && state.buggy && (
        <Step n={6} title="Regression verification" tone="good" refCb={ref("verify")}>
          <Verification reports={state.reports} headline={cfg.headlineInvariant} before={cfg.verifyBefore} after={cfg.verifyAfter} />
          <p className="mt-5 text-[15px] leading-relaxed text-ink-200">
            Each test just re-executed its version for real on this server, under the same failure, and checked the safety invariants. GhostReplay turns failures into repeatable tests, so the same bug can't quietly come back.
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

// -- building blocks ---------------------------------------------------------------------------

const ACTOR: Record<Actor, { label: string; cls: string }> = {
  model: { label: "Model decision", cls: "bg-violet-500/20 text-violet-100" },
  app: { label: "Application code", cls: "bg-sky-500/20 text-sky-100" },
  service: { label: "Service", cls: "bg-white/10 text-ink-100" },
  fault: { label: "Injected fault", cls: "bg-amber-400/20 text-amber-100" },
};

function Step({ n, title, children, tone = "neutral", refCb }: { n: number | string; title: string; children: ReactNode; tone?: "neutral" | "bad" | "good" | "info"; refCb: (el: HTMLElement | null) => void }) {
  const ring = { neutral: "ring-white/10", bad: "ring-rose-400/25", good: "ring-emerald-400/25", info: "ring-cyan-400/25" }[tone];
  const dot = { neutral: "bg-violet-500/80", bad: "bg-rose-500/80", good: "bg-emerald-500/80", info: "bg-cyan-500/80" }[tone];
  return (
    <section ref={refCb} className={cx("animate-fade mb-6 scroll-mt-24 rounded-2xl bg-ink-900/80 p-5 ring-1 sm:p-7", ring)} data-testid={`step-${n}`}>
      <div className="mb-4 flex items-center gap-3">
        <span className={cx("grid size-7 place-items-center rounded-full font-mono text-sm font-semibold text-white", dot)}>{n}</span>
        <h2 className="text-xl font-semibold text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Cta({ onClick, busy, disabled, label, testId }: { onClick: () => void; busy: boolean; disabled?: boolean; label: string; testId: string }) {
  return (
    <div className="mt-6">
      <button type="button" onClick={onClick} disabled={busy || disabled} data-testid={testId} className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-violet-500 to-violet-600 px-5 py-2.5 text-[15px] font-semibold text-white shadow-[0_0_0_1px_rgb(167_139_250/0.5),0_10px_30px_-10px_rgb(139_92_246/0.8)] transition-colors hover:from-violet-400 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50">
        {busy ? <Spinner /> : null}
        {busy ? "Running for real…" : `${label} →`}
      </button>
    </div>
  );
}

const Honesty = ({ children }: { children: ReactNode }) => <p className="mt-4 text-xs leading-relaxed text-ink-400">{children}</p>;

const DevLink = ({ href: to, children }: { href: string; children: ReactNode }) => (
  <a href={to} className="mt-3 inline-block text-sm text-cyan-300 underline-offset-4 hover:underline">Developer mode: {children} →</a>
);

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
  const tone = { bad: "bg-rose-500/[0.08] text-rose-100 ring-rose-400/25", warn: "bg-amber-400/[0.08] text-amber-100 ring-amber-400/25", good: "bg-emerald-500/[0.08] text-emerald-100 ring-emerald-400/25", neutral: "bg-white/[0.02] text-ink-200 ring-white/10" }[line.tone];
  const actor = ACTOR[line.actor];
  return (
    <li className={cx("flex flex-wrap items-start gap-x-3 gap-y-1 rounded-xl px-4 ring-1", compact ? "py-2 text-sm" : "py-3 text-[15px]", tone, compact && !line.key && "opacity-80")} data-actor={line.actor}>
      <span className="font-mono text-xs leading-6 opacity-60">{n}.</span>
      <span className={cx("mt-0.5 rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider", actor.cls)}>{actor.label}</span>
      <span className="min-w-0 flex-1 leading-relaxed">{line.text}</span>
      <span className="shrink-0 font-mono text-[10.5px] leading-6 opacity-50">seq {line.seq}</span>
    </li>
  );
}

function TechDetails({ ex, highlight }: { ex: Execution; highlight: string[] }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<GREvent>();
  return (
    <div className="mt-6">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-sm font-medium text-cyan-300 hover:text-cyan-200" data-testid="tech-details">
        {open ? "▾ Hide technical details" : "▸ Show technical details (model inputs and responses, tool arguments, HTTP results, state changes, errors, timing)"}
      </button>
      {open && (
        <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="rounded-xl ring-1 ring-white/10"><Timeline execution={ex} selected={selected?.event_id} onSelect={setSelected} highlight={highlight} compact /></div>
          <div className="rounded-xl ring-1 ring-white/10">{selected ? <Inspector event={selected} /> : <p className="p-4 text-sm text-ink-300">Select an event to inspect its request, response, state change and timing.</p>}</div>
        </div>
      )}
    </div>
  );
}

function ReplayFacts({ replay, diff }: { replay: Execution; diff?: TraceDiff }) {
  const ev = replayEvidence(replay);
  const facts: Fact[] = [
    { label: "Model calls avoided", value: String(ev.modelAvoided), tone: "cyan" },
    { label: "Tool calls avoided", value: String(ev.toolsAvoided), tone: "cyan" },
    { label: "Matched events", value: String(ev.matched), tone: "cyan" },
    { label: "Executed during replay", value: String(ev.executed), tone: ev.executed === 0 ? "green" : "red" },
  ];
  return (
    <div data-testid="replay-facts">
      <Facts facts={facts} />
      <p className="mt-3 text-sm text-ink-300">
        Divergence: <b className="text-white">{replay.divergence ? "yes" : "none"}</b> · status: <b className="text-white">{replay.status}</b> · compared with the original:{" "}
        <b className="text-white">{diff?.identical ? "identical" : "different"}</b> · same verdicts: {replay.invariants.filter((i) => i.status === "failed").map((i) => i.id).join(", ") || "no invariant failed"}.
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
            <th className="px-4 py-2.5 font-medium">Buggy version</th>
            <th className="px-4 py-2.5 font-medium">Fixed version</th>
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

function Verification({ reports, headline, before, after }: { reports: RegressionReport[]; headline: string; before: string; after: string }) {
  const b = reports.find((r) => r.variant === "vulnerable");
  const a = reports.find((r) => r.variant === "fixed");
  const card = (r: RegressionReport | undefined, label: "Before" | "After", text: string) => {
    if (!r) return <div className="rounded-xl p-4 ring-1 ring-white/10">No report for {label}.</div>;
    const inv = r.invariants.find((i) => i.id === headline);
    return (
      <div className={cx("rounded-xl p-5 ring-1", r.passed ? "bg-emerald-500/[0.07] ring-emerald-400/30" : "bg-rose-500/[0.07] ring-rose-400/30")} data-testid={`verify-${label.toLowerCase()}`} data-passed={r.passed}>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{label} · {r.variant} version</div>
        <div className={cx("mt-1 text-2xl font-bold", r.passed ? "text-emerald-300" : "text-rose-300")}>{r.passed ? "PASSED" : "FAILED"}</div>
        <p className="mt-2 text-[15px] text-ink-100">{r.outcome_matches_expectation ? text : "Unexpected result: see the report."}</p>
        {inv && <p className="mt-2 font-mono text-xs text-ink-300">{inv.id}: {inv.message}</p>}
        <p className="mt-1 text-xs text-ink-400">expected {r.expect.toUpperCase()} · {r.outcome_matches_expectation ? "as expected" : "NOT as expected"} · re-executed as {r.execution_id}</p>
      </div>
    );
  };
  return <div className="grid gap-3 sm:grid-cols-2">{card(b, "Before", before)}{card(a, "After", after)}</div>;
}

function SourceNote({ ex, lab }: { ex: Execution; lab: "support" | "devops" }) {
  return (
    <p className="mt-4 text-xs text-ink-400">
      Execution <a className="font-mono text-cyan-300 hover:underline" href={href({ name: "execution", lab, id: ex.id })}>{ex.id}</a> · {ex.events.length} events · re-executed from capture {ex.reference_execution_id} · decisions: {ex.provenance.label} · tools: {ex.provenance.tool_backends}
    </p>
  );
}
