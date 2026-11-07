import { LABS, type LabId } from "../api/client";
import { Badge, GhostLogo } from "../components/ui";
import { href } from "../lib/router";

const STEPS = [
  { n: "01", title: "Record", text: "Every model call, tool call, clock read and id is captured in order — redacted before it is stored.", tone: "text-sky-300" },
  { n: "02", title: "Replay", text: "Re-run the agent offline. Responses come from the recording; tools and network are physically blocked.", tone: "text-cyan-300" },
  { n: "03", title: "Break", text: "Inject a timeout-after-commit, a 429, stale data, a permission error… at any recorded step.", tone: "text-fuchsia-300" },
  { n: "04", title: "Detect", text: "Safety invariants flag the dangerous behaviour: double refunds, unverified destructive actions.", tone: "text-rose-300" },
  { n: "05", title: "Prove", text: "Fix the harness, re-run the same failure, and export a pytest regression that PASSES.", tone: "text-emerald-300" },
];

function DemoCard({ lab, primary }: { lab: LabId; primary?: boolean }) {
  const def = LABS[lab];
  return (
    <a
      href={href({ name: "story", lab })}
      className={
        "group relative block overflow-hidden rounded-2xl border p-6 transition-all duration-200 hover:-translate-y-0.5 " +
        (primary
          ? "border-violet-400/40 bg-gradient-to-br from-violet-500/[0.16] via-ink-900 to-ink-900 shadow-[0_20px_60px_-25px_rgb(139_92_246/0.7)] hover:border-violet-300/60"
          : "border-white/10 bg-ink-900/80 hover:border-cyan-300/40")
      }
    >
      <div className="flex items-center gap-2">
        <Badge tone={primary ? "violet" : "cyan"}>{def.name}</Badge>
        <Badge>one click · no setup · no API keys</Badge>
      </div>
      <div className="mt-4 text-xl font-semibold text-white">{def.demoLabel} →</div>
      <p className="mt-2 text-sm leading-relaxed text-ink-300">{def.tagline}</p>
      <div className="mt-5 flex items-center gap-2 font-mono text-[11px] text-ink-400">
        <span className="text-rose-300">incident FAIL</span>
        <span>→</span>
        <span className="text-cyan-300">replay identical</span>
        <span>→</span>
        <span className="text-fuchsia-300">inject fault</span>
        <span>→</span>
        <span className="text-emerald-300">fix PASS</span>
      </div>
      <span className="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-violet-500/10 blur-3xl transition-opacity group-hover:opacity-100" />
    </a>
  );
}

export function Home() {
  return (
    <div className="animate-fade">
      <section className="grid-bg relative -mx-5 -mt-8 overflow-hidden border-b hairline px-5 pb-14 pt-16">
        <div className="mx-auto max-w-[1500px]">
          <div className="flex items-center gap-3">
            <GhostLogo className="size-10" />
            <Badge tone="violet">open source · Python framework + dashboard</Badge>
          </div>
          <h1 className="mt-6 max-w-4xl text-5xl font-bold leading-[1.05] tracking-tight md:text-6xl">
            <span className="text-gradient">Break AI agents safely.</span>
            <br />
            <span className="text-white">Replay failures. Prove the fix.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-300">
            GhostReplay records what your agent actually did, replays it deterministically offline, injects the failures that
            happen in production, and turns the dangerous ones into regression tests.
          </p>
          <div className="mt-10 grid max-w-5xl gap-4 md:grid-cols-2">
            <DemoCard lab="support" primary />
            <DemoCard lab="devops" />
          </div>
        </div>
      </section>

      <section className="py-14">
        <div className="mb-8 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">How it works</div>
        <div className="grid gap-px overflow-hidden rounded-2xl border hairline bg-white/[0.06] md:grid-cols-5">
          {STEPS.map((s) => (
            <div key={s.n} className="bg-ink-900 p-5">
              <div className={`font-mono text-xs ${s.tone}`}>{s.n}</div>
              <div className="mt-2 text-base font-semibold text-white">{s.title}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-ink-300">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 pb-10 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-2xl border hairline bg-ink-900/80 p-6">
          <div className="text-sm font-semibold text-white">One door between the agent and the world</div>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-300">
            Agents call <code className="font-mono text-violet-300">rt.complete()</code>,{" "}
            <code className="font-mono text-violet-300">rt.call_tool()</code>, <code className="font-mono text-violet-300">rt.now()</code> and{" "}
            <code className="font-mono text-violet-300">rt.new_id()</code>. A single session decides — per call — whether to execute it,
            serve it from the recording, or inject a fault, and labels every event with where its response came from.
          </p>
          <pre className="mt-4 overflow-x-auto rounded-lg border hairline bg-ink-950 p-4 font-mono text-[12px] leading-relaxed text-ink-200">
{`agent ─▶ AgentRuntime ─▶ Session.interact(op)
                          ├─ record   → execute          `}<span className="text-sky-300">live</span>{`
                          ├─ replay   → recording        `}<span className="text-cyan-300">recorded</span>{`
                          ├─ fault    → substitute       `}<span className="text-fuchsia-300">injected</span>{`
                          └─ branch   → re-execute sim   `}<span className="text-violet-300">simulated</span>{`
                    divergence? ─▶ stop & report (never guess)`}
          </pre>
        </div>
        <div className="rounded-2xl border hairline bg-ink-900/80 p-6">
          <div className="text-sm font-semibold text-white">Honest by construction</div>
          <ul className="mt-3 space-y-2.5 text-[13px] leading-relaxed text-ink-300">
            <li><span className="text-cyan-300">●</span> Offline replay never invokes a tool or model; sockets are blocked on the replay thread.</li>
            <li><span className="text-amber-300">●</span> Divergence is reported at the exact step — recorded responses are never consumed out of order.</li>
            <li><span className="text-fuchsia-300">●</span> Faults that need a real side effect run in labelled branch mode, never as a made-up continuation.</li>
            <li><span className="text-emerald-300">●</span> Demo decisions come from scripted models and are labelled as such everywhere.</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
