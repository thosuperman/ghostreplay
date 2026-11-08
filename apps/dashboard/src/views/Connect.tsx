import type { ReactNode } from "react";
import ci from "../../../../docs/sdk/examples/github-actions.yml?raw";
import quickstart from "../../../../docs/sdk/examples/quickstart.py?raw";
import { CodeBlock } from "../components/CodeBlock";
import { Badge } from "../components/ui";
import { href } from "../lib/router";

const REPO = "https://github.com/thosuperman/ghost-replay";
const DOCS = `${REPO}/tree/main/docs/sdk`;

const STEPS = [
  { id: "install", title: "Install", text: "Add the Python SDK to your agent's environment (Python 3.12+, depends only on pydantic)." },
  { id: "instrument", title: "Instrument", text: "Decorate the functions your agent uses to reach the world: tools and model calls." },
  { id: "record", title: "Record", text: "Run the agent through GhostReplay. Every routed call is captured, redacted and stored." },
  { id: "replay", title: "Replay", text: "Re-run the same agent code offline. Recorded answers are served; your functions are not called." },
  { id: "debug", title: "Debug", text: "Inject failures, diff runs, and turn incidents into pytest regressions that run in CI." },
];

const LABELS = [
  ["Scripted demo", "Decisions come from a deterministic policy (developer-mode recordings and tests), not an LLM."],
  ["Genuine capture", "A run recorded with a live model against real local services, shipped read-only."],
  ["Live model call", "A real request to a model provider, made while recording. Opt-in only."],
  ["Recorded model response", "A model answer served from a recording during replay. No API call is made."],
  ["Mocked tool response", "A tool result served from the recording instead of executing the tool."],
  ["Strict replay", "The same agent code against the recording. Stops at the first divergence."],
  ["Controlled fault injection", "A labelled fault (a timeout, stale data, a replaced model decision) injected on purpose."],
  ["Re-execution / corrected re-execution", "Tools, HTTP and SQL run again for real; model decisions are served from the recording (branch mode)."],
];

export function Connect() {
  return (
    <div className="animate-fade mx-auto max-w-[1100px]" data-testid="connect-page">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">Bring your own agent</div>
      <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">Connect your own AI agent</h1>
      <p className="mt-3 max-w-3xl text-lg leading-relaxed text-ink-300">
        GhostReplay is a Python SDK. The two demos on this site are built with it, and so is a third, separate example app. Here is the whole workflow with code that runs exactly as shown.
      </p>

      <ol className="mt-8 grid gap-2 sm:grid-cols-5">
        {STEPS.map((s, i) => (
          <li key={s.id}>
            <a href={`#/connect`} onClick={(e) => { e.preventDefault(); document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" }); }} className="block h-full rounded-xl border hairline bg-ink-900/70 p-4 hover:border-violet-400/40">
              <div className="font-mono text-xs text-violet-300">{i + 1}</div>
              <div className="mt-0.5 font-semibold text-white">{s.title}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-300">{s.text}</p>
            </a>
          </li>
        ))}
      </ol>

      <Section id="install" title="1. Install">
        <p>Install from the repository. The SDK is not on PyPI yet.</p>
        <CodeBlock lang="bash" filename="shell" code={`pip install "ghostreplay @ git+${REPO}@main#subdirectory=packages/ghostreplay"\n\n# or from a local checkout\ngit clone ${REPO}.git\npip install ./ghost-replay/packages/ghostreplay`} />
        <p className="text-sm text-ink-400">Optional extras: <code className="font-mono">ghostreplay[server]</code> (HTTP API and dashboard backend) and <code className="font-mono">ghostreplay[live]</code> (Anthropic adapter for live LLM calls).</p>
      </Section>

      <Section id="instrument" title="2–5. Instrument, record, replay and prove a fix">
        <p>
          A complete agent: a model call, a payment tool, a buggy and a fixed agent, and one safety rule. It records a timeout-after-commit failure, replays it offline and runs the regression for both agents. It runs as-is with <code className="font-mono">python quickstart.py</code>.
        </p>
        <CodeBlock code={quickstart} filename="quickstart.py · tested in CI" />
        <p className="text-sm text-ink-300">Output:</p>
        <CodeBlock lang="text" filename="stdout" code={`rec_… [record] agent=buggy status=completed\n  output (success): charged\n  [FAIL] charges.at_most_once: customer charged 2 times\nreplay: completed, live calls 0\nbuggy: FAIL (expected FAIL)\nfixed: PASS (expected PASS)`} />
      </Section>

      <Section id="record" title="What gets recorded, and what does not">
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b className="text-white">Recorded:</b> calls to functions decorated with <code className="font-mono">@ghost.tool</code> and <code className="font-mono">@ghost.model</code>, <code className="font-mono">ghost.complete()</code> for model adapters, <code className="font-mono">ghost.new_id()</code>/<code className="font-mono">ghost.now()</code>, and <code className="font-mono">ghost.step()</code> annotations. Sync and async functions are both supported.</li>
          <li><b className="text-white">Not recorded:</b> anything else your code does, such as direct HTTP requests, database queries, the system clock or global state. A decorator on your agent function does not reach inside it. Route each external call through a decorated function.</li>
          <li>Arguments and results must be JSON-serialisable. Secret-looking values are redacted before anything is stored.</li>
          <li>Raise <code className="font-mono">ghostreplay.ToolTimeout</code>, <code className="font-mono">RateLimited</code>, <code className="font-mono">HttpError</code> and friends for failures you want recorded and replayed.</li>
        </ul>
      </Section>

      <Section id="replay" title="Command line">
        <CodeBlock
          lang="bash"
          filename="shell"
          code={`ghostreplay export RUN_ID --store ./ghostreplay-data --app shop-agent --out traces/\nghostreplay inspect traces/RUN_ID.trace.json          # what happened, verdicts\nghostreplay diff traces/A.trace.json traces/B.trace.json  # first divergence\nghostreplay replay traces/RUN_ID.trace.json --app quickstart:ghost  # strict offline replay\nghostreplay test tests/regression --import quickstart   # exit 1 on an unexpected outcome`}
        />
        <p className="text-sm text-ink-400">
          A trace is data. Replaying it always needs the agent code that produced it, passed explicitly with <code className="font-mono">--app</code>. Nothing in a trace can name code to run.
        </p>
      </Section>

      <Section id="debug" title="Run your regressions in CI">
        <p>The generated tests are plain pytest and run fully offline. CI fails when a safety invariant is violated.</p>
        <CodeBlock code={ci} lang="yaml" filename=".github/workflows/agent-regressions.yml" />
      </Section>

      <Section id="example" title="A complete external app: the Invoice Processing Agent">
        <p>
          <a className="text-cyan-300 hover:underline" href={`${REPO}/tree/main/examples/invoice-agent`}>examples/invoice-agent</a> is a separate project that uses only the public SDK. A payment commits but times out, the buggy agent pays the vendor twice, the replay reproduces it without calling the payment service, and the fixed agent passes the generated regression tests.
        </p>
        <CodeBlock lang="bash" filename="shell" code={`cd examples/invoice-agent\npip install ../../packages/ghostreplay -e ".[test]"\ninvoice-agent-demo        # the whole workflow, step by step\npytest                    # unit tests + generated regression tests`} />
      </Section>

      <Section id="hosted" title="Inspect a trace in the browser">
        <p>
          You can upload a GhostReplay trace file to inspect its timeline, events and verdicts here. Uploaded traces are private to your browser session, validated, redacted and deleted after 24 hours. This server never runs your code, so a trace from your own app can be inspected here but only replayed on your machine.
        </p>
        <a href={href({ name: "import" })} className="inline-block rounded-lg bg-white/[0.05] px-4 py-2 text-sm font-medium text-white ring-1 ring-white/15 hover:bg-white/[0.09]">Import a trace →</a>
      </Section>

      <Section id="labels" title="Labels you'll see">
        <dl className="grid gap-2 sm:grid-cols-2">
          {LABELS.map(([t, d]) => (
            <div key={t} className="rounded-lg bg-white/[0.03] px-4 py-3 ring-1 ring-white/10">
              <dt className="text-sm font-semibold text-white">{t}</dt>
              <dd className="mt-0.5 text-[13px] text-ink-300">{d}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <div className="mt-10 flex flex-wrap items-center gap-3 border-t hairline pt-6">
        <Badge tone="violet">Docs</Badge>
        <a className="text-sm text-cyan-300 hover:underline" href={DOCS}>Full SDK documentation (quickstart, API, instrumentation, replay, faults, regressions, CI, limitations) ↗</a>
      </div>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="mt-12 scroll-mt-24 space-y-4 text-[15px] leading-relaxed text-ink-200">
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      {children}
    </section>
  );
}
