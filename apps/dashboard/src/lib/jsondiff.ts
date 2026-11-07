import type { Change, Json } from "../api/types";

/** Structural diff of two JSON values (mirrors ghostreplay.core.canonical.deep_diff). */
export function jsonDiff(before: Json | undefined, after: Json | undefined, path = ""): Change[] {
  const join = (k: string | number) => (path ? `${path}.${k}` : String(k));
  if (Array.isArray(before) && Array.isArray(after)) {
    const out: Change[] = [];
    for (let i = 0; i < Math.max(before.length, after.length); i++) {
      if (i >= before.length) out.push({ path: join(i), op: "added", before: null, after: after[i] ?? null });
      else if (i >= after.length) out.push({ path: join(i), op: "removed", before: before[i] ?? null, after: null });
      else out.push(...jsonDiff(before[i], after[i], join(i)));
    }
    return out;
  }
  const isObj = (v: unknown): v is Record<string, Json> => typeof v === "object" && v !== null && !Array.isArray(v);
  if (isObj(before) && isObj(after)) {
    const out: Change[] = [];
    for (const k of [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()) {
      if (!(k in before)) out.push({ path: join(k), op: "added", before: null, after: after[k] ?? null });
      else if (!(k in after)) out.push({ path: join(k), op: "removed", before: before[k] ?? null, after: null });
      else out.push(...jsonDiff(before[k], after[k], join(k)));
    }
    return out;
  }
  if (JSON.stringify(before) !== JSON.stringify(after)) {
    return [{ path: path || "$", op: "changed", before: before ?? null, after: after ?? null }];
  }
  return [];
}
