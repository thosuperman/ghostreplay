import { useState, type ReactNode } from "react";
import { cx } from "./ui";

const KEYWORDS = new Set([
  "from", "import", "def", "async", "await", "return", "for", "in", "if", "else", "elif", "try", "except",
  "continue", "break", "class", "with", "as", "and", "or", "not", "is", "None", "True", "False", "lambda", "pass", "raise",
]);

/** Tiny tokenizer for Python and shell snippets: comments, strings, decorators, keywords. */
function highlight(code: string, lang: "python" | "bash" | "yaml" | "text") {
  if (lang === "text") return [<span key="0">{code}</span>];
  const out: ReactNode[] = [];
  const re = lang === "python"
    ? /(#[^\n]*)|("""[\s\S]*?"""|f?"(?:\\.|[^"\\\n])*"|f?'(?:\\.|[^'\\\n])*')|(@[\w.]+)|(\b[A-Za-z_]\w*\b)|(\s+|.)/g
    : /(#[^\n]*)|("(?:\\.|[^"\\\n])*"|'[^'\n]*')|(@[\w.]+)|(\b[A-Za-z_][\w-]*\b)|(\s+|.)/g;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(code))) {
    const [tok, comment, string, deco, word] = m;
    const cls = comment ? "text-ink-400 italic" : string ? "text-emerald-300" : deco ? "text-fuchsia-300" : word && lang === "python" && KEYWORDS.has(word) ? "text-violet-300" : word && lang === "bash" && /^(pip|uv|ghostreplay|python|pytest|git|cd|curl)$/.test(word) ? "text-cyan-300" : undefined;
    out.push(cls ? <span key={i++} className={cls}>{tok}</span> : <span key={i++}>{tok}</span>);
  }
  return out;
}

export function CodeBlock({ code, filename, lang = "python", className }: { code: string; filename?: string; lang?: "python" | "bash" | "yaml" | "text"; className?: string }) {
  const [copied, setCopied] = useState(false);
  const text = code.replace(/\n+$/, "");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (insecure context): the code stays selectable */
    }
  };
  return (
    <div className={cx("overflow-hidden rounded-xl border hairline bg-ink-950", className)}>
      <div className="flex items-center justify-between border-b hairline bg-white/[0.02] px-4 py-2">
        <span className="font-mono text-[11.5px] text-ink-400">{filename ?? lang}</span>
        <button type="button" onClick={() => void copy()} className="rounded-md px-2 py-0.5 text-[11.5px] text-ink-300 ring-1 ring-white/10 hover:text-white" aria-label="Copy code">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12.5px] leading-relaxed text-ink-100">
        <code>{highlight(text, lang)}</code>
      </pre>
    </div>
  );
}
