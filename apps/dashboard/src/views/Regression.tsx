import { useEffect, useState } from "react";
import { api, LABS, type LabId } from "../api/client";
import type { ExportedCase, RegressionReport } from "../api/types";
import { ExecutionPicker, InvariantList } from "../components/execution";
import { Badge, Button, Card, cx, Empty, ErrorBox, SectionHeader, Select, Spinner, Verdict } from "../components/ui";
import { ms } from "../lib/format";
import { href } from "../lib/router";
import { useAsync } from "../lib/useAsync";

export function Regression({ lab, initialId }: { lab: LabId; initialId?: string }) {
  const list = useAsync(() => api.executions(lab), [lab]);
  const scenarios = useAsync(() => api.scenarios(lab), [lab]);
  const [id, setId] = useState(initialId ?? "");
  const [reports, setReports] = useState<RegressionReport[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [exportVariant, setExportVariant] = useState("fixed");
  const [exported, setExported] = useState<ExportedCase>();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!id && list.data) {
      const cf = list.data.find((s) => s.mode === "branch" && s.injected_faults > 0);
      if (cf) setId(cf.id);
    }
  }, [list.data, id]);

  const run = async () => {
    setBusy(true);
    setError(undefined);
    setReports(undefined);
    try {
      setReports(await api.runRegression(lab, id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    setError(undefined);
    try {
      setExported(await api.exportCase(lab, id, exportVariant));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const download = (name: string, content: string, type: string) => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const sc = scenarios.data?.[0];
  return (
    <div className="animate-fade">
      <SectionHeader eyebrow={LABS[lab].name} title="Regression Results">
        Turn any execution — typically a counterfactual — into a reproducible regression case: scenario, conditions, faults and the reference
        recording, stored as plain JSON. Cases run under pytest and report PASS/FAIL per safety invariant.
      </SectionHeader>

      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-4 p-4">
          <div className="min-w-[24rem] flex-1">
            <ExecutionPicker label="Source execution" executions={list.data ?? []} value={id} onChange={(v) => { setId(v); setReports(undefined); setExported(undefined); }} />
          </div>
          <Button variant="primary" onClick={() => void run()} disabled={!id || busy}>
            {busy ? <><Spinner className="size-3.5" /> Running…</> : "▶ Run against every agent variant"}
          </Button>
        </div>
      </Card>

      {error && <div className="mb-5"><ErrorBox error={error} /></div>}
      {!id && list.data && <Empty title="No counterfactual executions yet">Run one in the Failure Lab or the guided demo.</Empty>}

      {reports && (
        <div className="mb-6 grid gap-5 lg:grid-cols-2">
          {reports.map((r) => (
            <Card
              key={r.case_id}
              className={cx("animate-rise", r.passed ? "border-emerald-400/25" : "border-rose-400/25")}
              title={<span className="flex items-center gap-2.5"><Verdict verdict={r.passed ? "pass" : "fail"} size="lg" /> <span className="font-mono text-[12.5px]">{r.case_id}</span></span>}
              subtitle={`variant ${r.variant} · ${r.mode} · ${ms(r.duration_ms)} simulated`}
              actions={
                <Badge tone={r.outcome_matches_expectation ? "green" : "red"} title="Vulnerable variants are expected to FAIL (the detector must catch the bug); fixed variants must PASS.">
                  expected {r.expect.toUpperCase()} {r.outcome_matches_expectation ? "✓" : "✕"}
                </Badge>
              }
            >
              <InvariantList invariants={r.invariants} />
              <div className="flex flex-wrap items-center gap-2 border-t hairline px-4 py-3">
                <Button href={href({ name: "execution", lab, id: r.execution_id })}>Open run</Button>
                {r.notes.map((n) => <span key={n} className="text-[11.5px] text-ink-400">{n}</span>)}
              </div>
            </Card>
          ))}
        </div>
      )}

      {id && (
        <Card
          title="Export as pytest"
          subtitle="Writes nothing to your repo — download the two files into tests/regression/ and run pytest."
          actions={
            <>
              {sc && <Select value={exportVariant} onChange={setExportVariant} options={sc.variants.map((v) => ({ value: v.id, label: `for ${v.id} agent` }))} />}
              <Button onClick={() => void doExport()}>Generate</Button>
            </>
          }
        >
          {exported ? (
            <div className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="violet">{exported.test_file}</Badge>
                <Badge>{exported.case_file}</Badge>
                <Button variant="primary" onClick={() => { download(exported.test_file, exported.pytest_source, "text/x-python"); download(exported.case_file, JSON.stringify(exported.case, null, 2), "application/json"); }}>
                  ↓ Download both
                </Button>
                <Button variant="ghost" onClick={() => { void navigator.clipboard.writeText(exported.pytest_source); setCopied(true); window.setTimeout(() => setCopied(false), 1500); }}>
                  {copied ? "Copied ✓" : "Copy test"}
                </Button>
              </div>
              <pre className="overflow-auto rounded-lg border hairline bg-ink-950 p-4 font-mono text-[12px] leading-relaxed text-ink-200">{exported.pytest_source}</pre>
              <pre className="rounded-lg border hairline bg-ink-950 p-3 font-mono text-[12px] text-cyan-200">{`uv run pytest tests/regression -q\nuv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json`}</pre>
            </div>
          ) : (
            <div className="p-4 text-sm text-ink-400">Generate the test module and its JSON case file for the selected execution.</div>
          )}
        </Card>
      )}
    </div>
  );
}
