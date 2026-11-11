import { useState } from "react";
import { api } from "../api/client";
import type { ImportResult } from "../api/types";
import { Badge, Button, Card, Empty, ErrorBox, Loading, ModeBadge, SectionHeader, StatusBadge } from "../components/ui";
import { ago } from "../lib/format";
import { href } from "../lib/router";
import { useAsync } from "../lib/useAsync";

const MAX_BYTES = 500 * 1024;
// Imports go to the Support lab's store; any GhostReplay trace can be inspected there.
const LAB = "support" as const;

export function ImportTrace() {
  const imported = useAsync(() => api.imported(LAB), []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<ImportResult>();

  const onFile = async (file: File | undefined) => {
    setError(undefined);
    setResult(undefined);
    if (!file) return;
    if (!/\.json$/i.test(file.name)) return setError("Choose a .json trace file (for example rec_1234.trace.json).");
    if (file.size > MAX_BYTES) return setError(`That file is ${(file.size / 1024).toFixed(0)} KB; the limit is ${MAX_BYTES / 1024} KB.`);
    const text = await file.text();
    try {
      JSON.parse(text);
    } catch {
      return setError("That file is not valid JSON.");
    }
    setBusy(true);
    try {
      const r = await api.importTrace(LAB, text);
      setResult(r);
      imported.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="animate-fade mx-auto max-w-4xl" data-testid="import-page">
      <SectionHeader eyebrow="Developer mode" title="Import a trace">
        Inspect a GhostReplay trace file in the dashboard: its timeline, every event, the injected faults and the safety verdicts.
      </SectionHeader>

      <Card title="Upload" subtitle={`.json trace files up to ${MAX_BYTES / 1024} KB, as written by ghostreplay export or GhostReplay.export().`}>
        <div className="p-5">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 bg-white/[0.02] px-6 py-10 text-center hover:border-violet-400/50">
            <span className="text-sm font-medium text-white">{busy ? "Validating…" : "Choose a trace file"}</span>
            <span className="text-xs text-ink-400">It is validated against the trace schema and never executed.</span>
            <input type="file" accept="application/json,.json" className="sr-only" data-testid="trace-file" disabled={busy} onChange={(e) => void onFile(e.target.files?.[0])} />
          </label>
          {error && <div className="mt-4" role="alert"><ErrorBox error={error} /></div>}
          {result && (
            <div className="mt-4 rounded-xl bg-emerald-500/[0.07] p-4 ring-1 ring-emerald-400/30" role="status" data-testid="import-result">
              <div className="flex flex-wrap items-center gap-2 text-sm text-white">
                Imported <span className="font-mono">{result.execution.id}</span>
                <Badge>{result.execution.app}</Badge>
                <ModeBadge mode={result.execution.mode} />
                <StatusBadge status={result.execution.status} />
              </div>
              <p className="mt-2 text-sm text-ink-200">{result.note}</p>
              <div className="mt-3">
                <Button variant="primary" href={href({ name: "execution", lab: LAB, id: result.execution.id })}>Inspect it →</Button>
              </div>
            </div>
          )}
        </div>
      </Card>

      <div className="mt-6 rounded-xl border hairline bg-ink-900/70 p-5 text-sm leading-relaxed text-ink-300">
        <div className="font-semibold text-white">What happens to an uploaded trace</div>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>The server validates it against the versioned schema (<code className="font-mono">ghostreplay/v1</code>), rejects anything malformed, and redacts secret-looking values again.</li>
          <li>It is stored only for your browser session and deleted after 24 hours (nightly backups are kept up to 14 days; see the Privacy Policy). Other visitors cannot see it.</li>
          <li>Nothing in it is executed. Traces from the two demo labs can be replayed here. A trace from your own agent can only be replayed where its code lives: <code className="font-mono">ghostreplay replay TRACE --app your_module:ghost</code>.</li>
        </ul>
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold text-white">Your imported traces</h2>
      {imported.loading && !imported.data && <Loading label="Loading…" />}
      {imported.error && <ErrorBox error={imported.error} />}
      {imported.data && imported.data.length === 0 && <Empty title="Nothing imported yet">Traces from other apps you upload appear here. Traces from the demo labs appear in their Execution Explorer.</Empty>}
      {imported.data && imported.data.length > 0 && (
        <ul className="divide-y divide-white/5 overflow-hidden rounded-xl border hairline bg-ink-900/70">
          {imported.data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <a className="font-mono text-cyan-300 hover:underline" href={href({ name: "execution", lab: LAB, id: s.id })}>{s.id}</a>
              <Badge>{s.app}</Badge>
              <span className="text-ink-300">{s.title || s.variant}</span>
              <span className="ml-auto text-xs text-ink-400">{s.invariants_failed ? `${s.invariants_failed} invariant(s) failed` : "no invariant failed"} · {ago(s.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
