import type { Execution, ExecutionSummary } from "../api/types";
import { executionTypes } from "../lib/executionType";
import { Badge } from "./ui";

export function ExecTypeBadges({ e, library }: { e: Execution | ExecutionSummary; library?: boolean }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-testid="exec-type">
      {executionTypes(e as Execution, { library }).map((t) => (
        <Badge key={t.label + t.detail} tone={t.tone} title={t.detail}>
          {t.label}
        </Badge>
      ))}
    </span>
  );
}
