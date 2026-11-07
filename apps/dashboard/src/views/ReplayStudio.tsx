import { useEffect, useMemo, useRef, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { Execution, ExecutionSummary, GREvent, TraceDiff } from "../api/types";
import { ExecutionPicker } from "../components/execution";
import { Badge, Button, Card, cx, Empty, ErrorBox, KindIcon, SectionHeader, SourceBadge, Spinner, Verdict, VerdictChip } from "../components/ui";
import { describe } from "../lib/format";
import { href } from "../lib/router";
import { useAsync } from "../lib/useAsync";

const INTERACTIONS = new Set(["model_call", "tool_call", "nondeterminism"]);

export function ReplayStudio({ lab, initialId }: { lab: LabId; initialId?: string }) {
  const list = useAsync(() => api.executions(lab), [lab]);
  const [recId, setRecId] = useState(initialId ?? "");
  const [delay, setDelay] = useState(260);
  const [recording, setRecording] = useState<Execution>();
  const [stream, setStream] = useState<GREvent[]>([]);
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<{ execution: ExecutionSummary; diff: TraceDiff }>();
  const [error, setError] = useState<string>();
  const source = useRef<EventSource | null>(null);
  const streamEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!recId && list.data) {
      const first = list.data.find((s) => s.mode === "record");
      if (first) setRecId(first.id);
    }
  }, [list.data, recId]);

  useEffect(() => {
    setRecording(undefined);
    reset();
    if (recId) api.execution(lab, recId).then(setRecording).catch((e: unknown) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lab, recId]);

  useEffect(() => () => source.current?.close(), []);
  useEffect(() => {
    void streamEnd.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [stream.length]);

  function reset() {
    source.current?.close();
    setStream([]);
    setResult(undefined);
    setState("idle");
    setError(undefined);
  }

  const start = () => {
    if (!recId) return;
    reset();
    setState("running");
    const es = new EventSource(api.replayStreamUrl(lab, recId, delay));
    source.current = es;
    es.addEventListener("event", (m) => setStream((s) => [...s, JSON.parse((m as MessageEvent<string>).data) as GREvent]));
    es.addEventListener("done", (m) => {
      setResult(JSON.parse((m as MessageEvent<string>).data) as { execution: ExecutionSummary; diff: TraceDiff });
      setState("done");
      es.close();
    });
    es.addEventListener("error", (m) => {
      const data = (m as MessageEvent<string>).data;
      es.close();
      if (data) {
        setError((JSON.parse(data) as { message: string }).message);
        setState("error");
      } else {
        setState((st) => {
          if (st === "running") setError("Lost the connection to the lab server during replay.");
          return st === "running" ? "error" : st;
        });
      }
    });
  };

  const served = useMemo(() => new Set(stream.map((e) => e.replay?.recorded_event_id).filter(Boolean) as string[]), [stream]);
  const lastServed = [...stream].reverse().find((e) => e.replay?.recorded_event_id)?.replay?.recorded_event_id;
  const recInteractions = recording?.events.filter((e) => INTERACTIONS.has(e.kind)) ?? [];
  const streamInteractions = stream.filter((e) => INTERACTIONS.has(e.kind));
  const progress = recInteractions.length ? (served.size / recInteractions.length) * 100 : 0;

  return (
    <div className="animate-fade">
      <SectionHeader eyebrow={LABS[lab].name} title="Replay Studio">
        Replays a recording through the real engine. Every row on the right is streamed by the server <em>as the replay engine records it</em>;
        the speed control slows the engine itself. No tool handler or model is invoked and the replay thread cannot open network connections.
      </SectionHeader>

      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-4 p-4">
          <div className="min-w-[24rem] flex-1">
            <ExecutionPicker label="Recording to replay" executions={list.data ?? []} value={recId} onChange={setRecId} filter={(s) => s.mode === "record"} />
          </div>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Engine pacing · {delay} ms/event</span>
            <input type="range" min={0} max={800} step={20} value={delay} onChange={(e) => setDelay(Number(e.target.value))} className="w-56 accent-cyan-400" />
          </label>
          <Button variant="primary" onClick={start} disabled={!recId || state === "running"}>
            {state === "running" ? <><Spinner className="size-3.5" /> Replaying…</> : "▶ Start offline replay"}
          </Button>
        </div>
        <div className="h-1 bg-white/[0.04]">
          <div className="h-1 bg-gradient-to-r from-cyan-400 to-violet-400 transition-[width] duration-200" style={{ width: `${state === "done" ? 100 : progress}%` }} />
        </div>
      </Card>

      {error && <div className="mb-5"><ErrorBox error={error} /></div>}
      {!recId && list.data && <Empty title="No recordings yet">Record a run in the Execution Explorer or run the guided demo first.</Empty>}

      {recording && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="Recording" subtitle={`${recInteractions.length} recorded interactions · ${recording.title || recording.id}`}>
            <ol>
              {recInteractions.map((e) => {
                const isServed = served.has(e.event_id);
                const isCursor = lastServed === e.event_id && state === "running";
                return (
                  <li key={e.event_id} className={cx("flex items-center gap-3 border-b hairline px-4 py-2 transition-colors duration-300", isServed ? "bg-cyan-400/[0.05]" : "opacity-60", isCursor && "bg-cyan-400/[0.12]")}>
                    <span className="w-8 font-mono text-[10.5px] text-ink-400">{e.seq}</span>
                    <KindIcon kind={e.kind} danger={e.destructive && !e.error} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[12.5px] text-ink-100">{e.name}</span>
                        {e.error && <Badge tone="red">{e.error.type}</Badge>}
                      </div>
                      <div className="truncate font-mono text-[10.5px] text-ink-400">{describe(e)}</div>
                    </div>
                    {isServed ? <span className="text-xs text-cyan-300">served ✓</span> : <span className="text-xs text-ink-500">pending</span>}
                  </li>
                );
              })}
            </ol>
          </Card>

          <Card
            title={<span className="flex items-center gap-2">Replay engine {state === "running" && <span className="size-2 animate-[pulse-ring_1.8s_ease-out_infinite] rounded-full bg-cyan-300" />}</span>}
            subtitle={`${stream.length} events emitted · ${streamInteractions.filter((e) => e.replay?.verdict === "matched").length} interactions matched`}
          >
            {stream.length === 0 && state === "idle" && <div className="p-6 text-sm text-ink-400">Press “Start offline replay”.</div>}
            <ol>
              {stream.map((e) => (
                <li key={e.event_id} className="flex animate-rise items-center gap-3 border-b hairline px-4 py-2">
                  <span className="w-8 font-mono text-[10.5px] text-ink-400">{e.seq}</span>
                  <KindIcon kind={e.kind} danger={e.destructive && !e.error} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-[12.5px] text-ink-100">{e.name}</span>
                      {e.error && <Badge tone="red">{e.error.type} (recorded)</Badge>}
                      {e.kind === "divergence" && <Badge tone="amber">divergence</Badge>}
                    </div>
                    <div className="truncate font-mono text-[10.5px] text-ink-400">{describe(e)}</div>
                  </div>
                  {e.replay ? <VerdictChip verdict={e.replay.verdict} /> : <SourceBadge source={e.source} />}
                </li>
              ))}
            </ol>
            <div ref={streamEnd} />
            {result && (
              <div className="animate-rise border-t hairline bg-ink-950/60 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Verdict verdict={result.diff.identical ? "pass" : "diverged"} size="lg" />
                  <span className="text-[13px] text-ink-100">
                    {result.diff.identical
                      ? "Replay is structurally identical to the recording (requests, responses, errors, timestamps)."
                      : `Replay diverged: ${result.diff.first_divergence?.summary ?? "see diff"}`}
                  </span>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button href={href({ name: "execution", lab, id: result.execution.id })}>Open replay execution</Button>
                  <Button href={href({ name: "diff", lab, a: recId, b: result.execution.id })}>Diff recording ↔ replay</Button>
                  <Button href={href({ name: "failure-lab", lab, id: recId })}>⚡ Break it in the Failure Lab</Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
