import { useEffect, useState } from "react";
import { api, LABS, type LabId } from "./api/client";
import type { LiveModelInfo } from "./api/types";
import { Badge, cx, Dot, GhostLogo } from "./components/ui";
import { href, type Route, useRoute } from "./lib/router";
import { DiffView } from "./views/DiffView";
import { ExecutionView } from "./views/ExecutionView";
import { Explorer } from "./views/Explorer";
import { FailureLab } from "./views/FailureLab";
import { Home } from "./views/Home";
import { Regression } from "./views/Regression";
import { ReplayStudio } from "./views/ReplayStudio";
import { Story } from "./views/Story";

type Health = Record<LabId, "up" | "down" | "checking">;

/** Show developer start commands only when the dashboard itself is served locally. */
const IS_LOCAL = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);

function useLabHealth(): { health: Health; live: Partial<Record<LabId, LiveModelInfo | null>> } {
  const [health, setHealth] = useState<Health>({ support: "checking", devops: "checking" });
  const [live, setLive] = useState<Partial<Record<LabId, LiveModelInfo | null>>>({});
  useEffect(() => {
    let alive = true;
    const check = () => {
      (Object.keys(LABS) as LabId[]).forEach((lab) => {
        api
          .info(lab)
          .then((info) => {
            if (!alive) return;
            setHealth((h) => ({ ...h, [lab]: "up" }));
            setLive((l) => ({ ...l, [lab]: info.live_model ?? null }));
          })
          .catch(() => alive && setHealth((h) => ({ ...h, [lab]: "down" })));
      });
    };
    check();
    const t = window.setInterval(check, 8000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);
  return { health, live };
}

const NAV: { name: Route["name"]; label: string }[] = [
  { name: "story", label: "Guided demo" },
  { name: "executions", label: "Executions" },
  { name: "replay", label: "Replay Studio" },
  { name: "failure-lab", label: "Failure Lab" },
  { name: "diff", label: "Diff" },
  { name: "regression", label: "Regression" },
];

function labOf(route: Route): LabId | undefined {
  return route.name === "home" ? undefined : route.lab;
}

function navHref(name: Route["name"], lab: LabId): string {
  return href({ name, lab } as Route);
}

export function App() {
  const route = useRoute();
  const { health, live } = useLabHealth();
  const lab = labOf(route);
  const liveModel = lab ? live[lab] : undefined;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b hairline bg-ink-950/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-[1500px] items-center gap-6 px-5">
          <a href="#/" className="flex shrink-0 items-center gap-2.5">
            <GhostLogo className="size-7" />
            <span className="text-[15px] font-semibold tracking-tight text-white">
              GhostReplay <span className="font-normal text-ink-300">Lab</span>
            </span>
          </a>

          <div className="flex shrink-0 items-center rounded-lg bg-white/[0.03] p-0.5 ring-1 ring-white/10">
            {(Object.keys(LABS) as LabId[]).map((id) => {
              const section = route.name === "home" ? "story" : route.name === "execution" ? "executions" : route.name;
              const safeTarget = { name: section, lab: id } as Route;
              return (
                <a
                  key={id}
                  href={href(safeTarget)}
                  className={cx(
                    "flex items-center gap-2 rounded-md px-3 py-1 text-[12.5px] font-medium transition-colors",
                    lab === id ? "bg-white/[0.09] text-white" : "text-ink-300 hover:text-white",
                  )}
                  title={
                    health[id] !== "down"
                      ? LABS[id].name
                      : IS_LOCAL
                        ? `${LABS[id].name} is offline — run: uv run ${id}-agent-lab serve`
                        : `${LABS[id].name} is temporarily unavailable`
                  }
                >
                  <Dot tone={health[id] === "up" ? "green" : health[id] === "down" ? "red" : "neutral"} pulse={health[id] === "checking"} />
                  {LABS[id].name}
                </a>
              );
            })}
          </div>

          {lab && (
            <nav className="hidden min-w-0 items-center gap-1 lg:flex">
              {NAV.map((n) => {
                const active = route.name === n.name || (n.name === "executions" && route.name === "execution");
                return (
                  <a
                    key={n.name}
                    href={navHref(n.name, lab)}
                    className={cx(
                      "relative rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                      active ? "text-white" : "text-ink-300 hover:text-white",
                    )}
                  >
                    {n.label}
                    {active && <span className="absolute inset-x-2.5 -bottom-[13px] h-px bg-gradient-to-r from-violet-400 to-cyan-300" />}
                  </a>
                );
              })}
            </nav>
          )}

          <div className="ml-auto hidden items-center gap-2 xl:flex">
            <Badge tone="cyan" title="All tools are in-memory simulations; replay blocks network access.">offline · simulated backends</Badge>
            {liveModel ? (
              <Badge tone="violet" title={`Scripted models by default; live AI (${liveModel.provider} ${liveModel.model}) can be chosen when recording.`}>
                scripted · live AI available
              </Badge>
            ) : (
              <Badge tone="amber" title="Decisions come from deterministic scripted models, not a live LLM.">scripted models</Badge>
            )}
          </div>
        </div>
        {lab && (
          <nav className="flex gap-1 overflow-x-auto border-t hairline px-4 py-1.5 lg:hidden">
            {NAV.map((n) => (
              <a key={n.name} href={navHref(n.name, lab)} className="whitespace-nowrap rounded-md px-2 py-1 text-xs text-ink-300 hover:text-white">
                {n.label}
              </a>
            ))}
          </nav>
        )}
      </header>

      {lab && health[lab] === "down" && (
        <div className="border-b border-amber-400/20 bg-amber-400/[0.06] px-5 py-2 text-center text-[13px] text-amber-200">
          {IS_LOCAL ? (
            <>
              {LABS[lab].name} is not running. Start it with{" "}
              <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-xs">uv run {lab}-agent-lab serve</code>
            </>
          ) : (
            <>{LABS[lab].name} is temporarily unavailable. It restarts automatically; please retry in a moment.</>
          )}
        </div>
      )}

      <main className="mx-auto max-w-[1500px] px-5 py-8">
        <View route={route} />
      </main>
    </div>
  );
}

function View({ route }: { route: Route }) {
  switch (route.name) {
    case "home":
      return <Home />;
    case "story":
      return <Story key={route.lab} lab={route.lab} />;
    case "executions":
      return <Explorer key={route.lab} lab={route.lab} />;
    case "execution":
      return <ExecutionView key={`${route.lab}:${route.id}`} lab={route.lab} id={route.id} focus={route.focus} />;
    case "replay":
      return <ReplayStudio key={`${route.lab}:${route.id ?? ""}`} lab={route.lab} initialId={route.id} />;
    case "failure-lab":
      return <FailureLab key={`${route.lab}:${route.id ?? ""}`} lab={route.lab} initialId={route.id} />;
    case "diff":
      return <DiffView key={`${route.lab}:${route.a ?? ""}:${route.b ?? ""}`} lab={route.lab} a={route.a} b={route.b} />;
    case "regression":
      return <Regression key={`${route.lab}:${route.id ?? ""}`} lab={route.lab} initialId={route.id} />;
  }
}
