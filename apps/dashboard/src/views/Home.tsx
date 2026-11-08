import hello from "../../../../docs/sdk/examples/hello.py?raw";
import { Badge, GhostLogo } from "../components/ui";
import { CodeBlock } from "../components/CodeBlock";
import { href } from "../lib/router";

const FLOW = [
  { n: "1", title: "Record", text: "Capture every decision your agent makes and every tool it calls, in order, like a flight recorder.", tone: "text-sky-300" },
  { n: "2", title: "Replay", text: "Run the same incident again offline. Recorded answers are reused, so no payment or server is touched twice.", tone: "text-cyan-300" },
  { n: "3", title: "Investigate", text: "See exactly which step went wrong, in plain English, with the full technical detail one click away.", tone: "text-fuchsia-300" },
  { n: "4", title: "Fix", text: "Change the agent and run it against the same failure, a timeout, stale data, an outage, on purpose.", tone: "text-amber-300" },
  { n: "5", title: "Verify", text: "Turn the incident into a regression test that fails for the bug and passes for the fix, in CI, forever.", tone: "text-emerald-300" },
];

const SCENARIOS = [
  {
    demo: "refund" as const,
    tag: "Support Agent",
    title: "The $129 Refund That Became $258",
    text: "A customer requested a $129 refund. Claude asked for one refund; the refund service committed it but the response timed out, and the app's retry refunded twice. See how GhostReplay detects and prevents the mistake.",
    cta: "Try Refund Demo",
    accent: "from-rose-500/[0.16] border-rose-400/30 hover:border-rose-300/60",
    before: "$258 refunded",
    after: "$129 refunded",
  },
  {
    demo: "devops" as const,
    tag: "DevOps Agent",
    title: "The AI Agent That Tried to Delete Healthy Servers",
    text: "An auto-remediation workflow trusts stale monitoring data and may terminate healthy instances. In our live run, Claude refused. GhostReplay then tests the workflow itself: what happens if the model does follow the runbook?",
    cta: "Try DevOps Demo",
    accent: "from-amber-500/[0.14] border-amber-400/30 hover:border-amber-300/60",
    before: "v1 + injected decision: 3 healthy servers shut down",
    after: "v2: blocked · human approval requested",
  },
];

export function Home() {
  return (
    <div className="animate-fade">
      <section className="grid-bg relative -mx-5 -mt-8 overflow-hidden border-b hairline px-5 pb-16 pt-14 sm:pt-20">
        <div className="mx-auto max-w-[1100px]">
          <div className="flex flex-wrap items-center gap-3">
            <GhostLogo className="size-10" />
            <Badge tone="violet">A flight recorder and crash-test lab for AI agents</Badge>
          </div>
          <h1 className="mt-6 max-w-4xl text-4xl font-bold leading-[1.05] tracking-tight text-white sm:text-5xl md:text-6xl">
            Your AI Agent Made a Mistake. <span className="text-gradient">Now What?</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-200 sm:text-xl">
            Record every decision, replay the failure safely, and prove your fix before it happens again.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href={href({ name: "demo", demo: "refund" })}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-violet-500 to-violet-600 px-6 py-3 text-base font-semibold text-white shadow-[0_0_0_1px_rgb(167_139_250/0.5),0_14px_40px_-12px_rgb(139_92_246/0.9)] hover:from-violet-400 hover:to-violet-500"
              data-testid="cta-watch-fail"
            >
              Watch an AI Agent Fail →
            </a>
            <a
              href={href({ name: "connect" })}
              className="inline-flex items-center gap-2 rounded-xl bg-white/[0.05] px-6 py-3 text-base font-semibold text-white ring-1 ring-inset ring-white/15 hover:bg-white/[0.09]"
              data-testid="cta-connect"
            >
              Connect Your Own Agent
            </a>
          </div>
          <p className="mt-6 font-mono text-sm text-ink-400">Catch the bug. Replay the failure. Prove the fix.</p>
        </div>
      </section>

      <section className="mx-auto mt-14 max-w-[1100px]">
        <h2 className="text-2xl font-semibold tracking-tight text-white">See a real agent fail, then watch the fix hold</h2>
        <p className="mt-2 max-w-2xl text-ink-300">Two AI agents, two expensive mistakes. The model's decisions come from genuine runs of Claude; every refund, database write, health check and termination you'll see is executed for real on this server, against isolated test services. No sign-up and no API keys.</p>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {SCENARIOS.map((s) => (
            <a key={s.demo} href={href({ name: "demo", demo: s.demo })} className={`group block rounded-2xl border bg-gradient-to-br via-ink-900 to-ink-900 p-6 transition-all hover:-translate-y-0.5 ${s.accent}`} data-testid={`scenario-${s.demo}`}>
              <Badge>{s.tag}</Badge>
              <h3 className="mt-4 text-xl font-semibold text-white">{s.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ink-300">{s.text}</p>
              <div className="mt-5 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-rose-200 ring-1 ring-rose-400/20">
                  <div className="text-[10.5px] uppercase tracking-wider opacity-70">Buggy agent</div>
                  {s.before}
                </div>
                <div className="rounded-lg bg-emerald-500/10 px-3 py-2 text-emerald-200 ring-1 ring-emerald-400/20">
                  <div className="text-[10.5px] uppercase tracking-wider opacity-70">Fixed agent</div>
                  {s.after}
                </div>
              </div>
              <div className="mt-5 text-[15px] font-semibold text-violet-200 group-hover:text-white">{s.cta} →</div>
            </a>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-400">The outcomes on these cards are what the demos reproduce; each run shows its own measured results.</p>
      </section>

      <section className="mx-auto mt-16 max-w-[1100px]">
        <h2 className="text-2xl font-semibold tracking-tight text-white">How it works</h2>
        <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {FLOW.map((s, i) => (
            <li key={s.n} className="relative rounded-xl border hairline bg-ink-900/70 p-4">
              <div className={`font-mono text-xs ${s.tone}`}>{s.n}</div>
              <div className="mt-1 text-lg font-semibold text-white">
                {s.title}
                {i < FLOW.length - 1 && <span className="ml-2 hidden text-ink-500 lg:inline">→</span>}
              </div>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-300">{s.text}</p>
            </li>
          ))}
        </ol>
        <div className="mt-6 grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border hairline bg-ink-900/70 p-5">
            <div className="text-sm font-semibold text-white">Why not just read the logs?</div>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-300">
              Logs tell you what happened once. GhostReplay lets you run it again: the same decisions, the same tool answers, on demand, without repeating the side effects. Then it injects the failure on purpose and tells you whether your fix really holds.
            </p>
          </div>
          <div className="rounded-xl border hairline bg-ink-900/70 p-5">
            <div className="text-sm font-semibold text-white">Who it's for</div>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-300">
              Developers building agents that take actions: AI agent and LLM application engineers, backend and DevOps automation teams, and QA engineers who need agent failures to be reproducible and testable.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto mt-16 max-w-[1100px]">
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-white">Works with your AI agent</h2>
            <p className="mt-3 text-ink-300">
              Install the Python SDK and decorate the calls your agent makes to the outside world: tools, and model calls. GhostReplay records exactly those calls, replays them offline, injects failures into them and turns incidents into pytest regressions.
            </p>
            <p className="mt-3 text-sm text-ink-400">
              It records only what you route through it. There is no automatic instrumentation of arbitrary code.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <a href={href({ name: "connect" })} className="rounded-lg bg-violet-500/90 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-400">Developer quickstart →</a>
              <a href={href({ name: "executions", lab: "support" })} className="rounded-lg px-4 py-2 text-sm font-medium text-ink-200 ring-1 ring-white/15 hover:bg-white/[0.05]">Open developer mode</a>
            </div>
          </div>
          <CodeBlock code={hello} filename="hello.py · runs as shown" />
        </div>
      </section>

      <footer className="mx-auto mt-16 max-w-[1100px] border-t hairline pt-6 text-xs leading-relaxed text-ink-400">
        Guided demos re-execute genuine recorded Claude runs (this public server makes no paid model calls); tools run for real against isolated services on this server (SQLite, a local refund service, a local instance lab) with fictional test data. No real payment, refund or cloud operation ever happens, and every execution is labelled with what was live, recorded, scripted or injected. Open source under the MIT license ·{" "}
        <a className="text-cyan-300 hover:underline" href="https://github.com/thosuperman/ghost-replay">GitHub</a>
      </footer>
    </div>
  );
}
