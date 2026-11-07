import type { ReactNode } from "react";
import type {
  EventKind,
  EventSource,
  ExecutionMode,
  ExecutionStatus,
  InvariantStatus,
  Json,
  ReplayVerdict,
} from "../api/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Tone = "neutral" | "violet" | "cyan" | "green" | "amber" | "red" | "fuchsia" | "blue";

const TONES: Record<Tone, string> = {
  neutral: "bg-white/[0.04] text-ink-200 ring-white/10",
  violet: "bg-violet-500/10 text-violet-300 ring-violet-400/25",
  cyan: "bg-cyan-400/10 text-cyan-300 ring-cyan-300/25",
  green: "bg-emerald-400/10 text-emerald-300 ring-emerald-300/25",
  amber: "bg-amber-400/10 text-amber-300 ring-amber-300/25",
  red: "bg-rose-500/10 text-rose-300 ring-rose-400/30",
  fuchsia: "bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-400/30",
  blue: "bg-sky-400/10 text-sky-300 ring-sky-300/25",
};

export function Badge({ tone = "neutral", children, title, className }: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone, pulse }: { tone: Tone; pulse?: boolean }) {
  const color: Record<Tone, string> = {
    neutral: "bg-ink-400",
    violet: "bg-violet-400",
    cyan: "bg-cyan-300",
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-rose-400",
    fuchsia: "bg-fuchsia-400",
    blue: "bg-sky-400",
  };
  return <span className={cx("inline-block size-2 rounded-full", color[tone], pulse && "animate-pulse")} />;
}

export function Verdict({ verdict, size = "md" }: { verdict: "pass" | "fail" | "info" | "diverged" | "inconclusive"; size?: "md" | "lg" }) {
  const map = {
    pass: { tone: "green" as Tone, label: "PASS" },
    fail: { tone: "red" as Tone, label: "FAIL" },
    info: { tone: "violet" as Tone, label: "WHY" },
    diverged: { tone: "amber" as Tone, label: "DIVERGED" },
    inconclusive: { tone: "amber" as Tone, label: "INCONCLUSIVE" },
  }[verdict];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md font-mono font-semibold tracking-wider ring-1 ring-inset",
        TONES[map.tone],
        size === "lg" ? "px-2.5 py-1 text-xs" : "px-1.5 py-0.5 text-[10px]",
      )}
    >
      <Dot tone={map.tone} />
      {map.label}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: ExecutionMode }) {
  const map: Record<ExecutionMode, { tone: Tone; label: string; title: string }> = {
    record: { tone: "blue", label: "recorded", title: "Live execution against simulated backends, recorded." },
    replay: { tone: "cyan", label: "offline replay", title: "Deterministic offline replay. Nothing was executed." },
    "counterfactual-replay": {
      tone: "fuchsia",
      label: "counterfactual · offline",
      title: "Offline replay with injected faults. Stops at the first divergence.",
    },
    branch: {
      tone: "violet",
      label: "counterfactual · branch",
      title: "Replayed prefix, then re-executed against a fresh simulated environment.",
    },
  };
  const m = map[mode];
  return (
    <Badge tone={m.tone} title={m.title}>
      {m.label}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: ExecutionStatus }) {
  const tone: Record<ExecutionStatus, Tone> = { running: "blue", completed: "neutral", failed: "red", diverged: "amber" };
  return <Badge tone={tone[status]}>{status}</Badge>;
}

export function SourceBadge({ source }: { source: EventSource }) {
  const map: Record<EventSource, { tone: Tone; title: string }> = {
    live: { tone: "blue", title: "Executed by the real implementation (simulated backend) while recording" },
    recorded: { tone: "cyan", title: "Served from the recording — nothing was executed" },
    injected: { tone: "fuchsia", title: "Synthesised or altered by fault injection" },
    simulated: { tone: "violet", title: "Re-executed against a simulated backend in branch mode" },
    framework: { tone: "neutral", title: "Bookkeeping produced by GhostReplay" },
  };
  return (
    <Badge tone={map[source].tone} title={map[source].title}>
      {source}
    </Badge>
  );
}

export function VerdictChip({ verdict }: { verdict: ReplayVerdict }) {
  const map: Record<ReplayVerdict, { tone: Tone; label: string }> = {
    matched: { tone: "cyan", label: "✓ matched" },
    substituted: { tone: "fuchsia", label: "⚡ substituted" },
    diverged: { tone: "amber", label: "≠ diverged" },
    live: { tone: "violet", label: "▶ new execution" },
  };
  return <Badge tone={map[verdict].tone}>{map[verdict].label}</Badge>;
}

export function InvariantBadge({ status }: { status: InvariantStatus }) {
  if (status === "passed") return <Verdict verdict="pass" />;
  if (status === "failed") return <Verdict verdict="fail" />;
  return <Verdict verdict="inconclusive" />;
}

const KIND_STYLE: Record<EventKind, { color: string; glyph: string; label: string }> = {
  execution_start: { color: "text-ink-300 border-ink-500", glyph: "◆", label: "start" },
  model_call: { color: "text-violet-300 border-violet-400/60", glyph: "✦", label: "model" },
  tool_call: { color: "text-sky-300 border-sky-400/60", glyph: "⚙", label: "tool" },
  nondeterminism: { color: "text-ink-300 border-ink-500", glyph: "⟳", label: "nondet" },
  agent_step: { color: "text-amber-200 border-amber-300/50", glyph: "↳", label: "step" },
  guard: { color: "text-emerald-300 border-emerald-400/60", glyph: "⛨", label: "guard" },
  state_snapshot: { color: "text-ink-300 border-ink-500", glyph: "▣", label: "state" },
  divergence: { color: "text-amber-300 border-amber-400/70", glyph: "≠", label: "diverge" },
  error: { color: "text-rose-300 border-rose-400/70", glyph: "✕", label: "error" },
  execution_end: { color: "text-ink-300 border-ink-500", glyph: "■", label: "end" },
};

export function KindIcon({ kind, danger }: { kind: EventKind; danger?: boolean }) {
  const s = KIND_STYLE[kind];
  return (
    <span
      title={s.label}
      className={cx(
        "grid size-6 shrink-0 place-items-center rounded-md border bg-ink-900 text-[11px]",
        danger ? "border-rose-400/70 text-rose-300" : s.color,
      )}
    >
      {s.glyph}
    </span>
  );
}

export function kindLabel(kind: EventKind): string {
  return KIND_STYLE[kind].label;
}

export function Card({ children, className, title, actions, subtitle }: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={cx("rounded-xl border hairline bg-ink-900/80 shadow-[0_1px_0_rgb(255_255_255/0.03)_inset]", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b hairline px-4 py-3">
          <div className="min-w-0">
            <h3 className="text-[13px] font-semibold tracking-wide text-ink-100">{title}</h3>
            {subtitle && <p className="mt-0.5 text-xs text-ink-300">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Button({ children, onClick, variant = "secondary", disabled, href, className, type = "button", title }: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  href?: string;
  className?: string;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles = {
    primary:
      "bg-gradient-to-b from-violet-500 to-violet-600 text-white shadow-[0_0_0_1px_rgb(167_139_250/0.5),0_8px_24px_-8px_rgb(139_92_246/0.7)] hover:from-violet-400 hover:to-violet-500",
    secondary: "bg-white/[0.04] text-ink-100 ring-1 ring-inset ring-white/10 hover:bg-white/[0.08]",
    ghost: "text-ink-200 hover:bg-white/[0.05] hover:text-white",
    danger: "bg-rose-500/10 text-rose-300 ring-1 ring-inset ring-rose-400/30 hover:bg-rose-500/20",
  }[variant];
  const cls = cx(
    "inline-flex items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40",
    styles,
    className,
  );
  if (href) {
    return (
      <a href={href} className={cls} title={title}>
        {children}
      </a>
    );
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={cls} title={title}>
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx("inline-block size-4 animate-spin rounded-full border-2 border-white/20 border-t-cyan-300", className)}
      aria-label="loading"
    />
  );
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-rose-400/30 bg-rose-500/[0.07] px-4 py-3 text-sm text-rose-200">
      <div className="font-semibold">Something went wrong</div>
      <div className="mt-1 font-mono text-xs text-rose-200/80">{error}</div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-white/10 px-6 py-14 text-center">
      <div className="text-sm font-semibold text-ink-200">{title}</div>
      {children && <div className="mt-2 max-w-md text-sm text-ink-300">{children}</div>}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 px-1 py-10 text-sm text-ink-300">
      <Spinner />
      {label}
    </div>
  );
}

export function Select<T extends string>({ value, onChange, options, className, label }: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  className?: string;
  label?: string;
}) {
  return (
    <label className={cx("flex flex-col gap-1", className)}>
      {label && <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="min-w-0 rounded-lg border hairline bg-ink-850 px-2.5 py-1.5 text-[13px] text-ink-100 outline-none focus:border-violet-400/60"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function JsonView({ value, className, maxHeight = "28rem" }: { value: Json | undefined; className?: string; maxHeight?: string }) {
  if (value === undefined) return <span className="text-xs text-ink-400">—</span>;
  return (
    <pre
      className={cx("overflow-auto rounded-lg border hairline bg-ink-950/80 p-3 font-mono text-[11.5px] leading-relaxed text-ink-200", className)}
      style={{ maxHeight }}
    >
      <JsonNode value={value} indent={0} />
    </pre>
  );
}

function JsonNode({ value, indent }: { value: Json; indent: number }): ReactNode {
  const pad = "  ".repeat(indent);
  const padIn = "  ".repeat(indent + 1);
  if (value === null) return <span className="json-null">null</span>;
  if (typeof value === "string") return <span className="json-string">{JSON.stringify(value)}</span>;
  if (typeof value === "number") return <span className="json-number">{value}</span>;
  if (typeof value === "boolean") return <span className="json-bool">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>[]</span>;
    return (
      <>
        {"[\n"}
        {value.map((v, i) => (
          <span key={i}>
            {padIn}
            <JsonNode value={v} indent={indent + 1} />
            {i < value.length - 1 ? ",\n" : "\n"}
          </span>
        ))}
        {pad}]
      </>
    );
  }
  const entries = Object.entries(value);
  if (entries.length === 0) return <span>{"{}"}</span>;
  return (
    <>
      {"{\n"}
      {entries.map(([k, v], i) => (
        <span key={k}>
          {padIn}
          <span className="json-key">{JSON.stringify(k)}</span>: <JsonNode value={v} indent={indent + 1} />
          {i < entries.length - 1 ? ",\n" : "\n"}
        </span>
      ))}
      {pad}
      {"}"}
    </>
  );
}

export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: "red" | "green" | "amber" | "cyan"; hint?: string }) {
  const color = tone
    ? { red: "text-rose-300", green: "text-emerald-300", amber: "text-amber-300", cyan: "text-cyan-300" }[tone]
    : "text-ink-100";
  return (
    <div className="min-w-0" title={hint}>
      <div className="text-[11px] font-medium uppercase tracking-wider text-ink-400">{label}</div>
      <div className={cx("mt-1 truncate font-mono text-lg font-semibold", color)}>{value}</div>
    </div>
  );
}

export function SectionHeader({ eyebrow, title, children, actions }: {
  eyebrow?: string;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
        {children && <div className="mt-2 text-sm leading-relaxed text-ink-300">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function GhostLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id="gl" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#a78bfa" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <path
        d="M16 3C9.9 3 6 7.6 6 13.5V27l3.3-2.4L12.7 27l3.3-2.4 3.3 2.4 3.4-2.4L26 27V13.5C26 7.6 22.1 3 16 3z"
        fill="url(#gl)"
      />
      <circle cx="12.5" cy="13.5" r="2" fill="#07080d" />
      <circle cx="19.5" cy="13.5" r="2" fill="#07080d" />
    </svg>
  );
}
