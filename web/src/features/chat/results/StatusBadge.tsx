import "./ResultsPanels.css";

interface StatusBadgeProps {
  executionMs: number | null | undefined;
  confidence: number | null | undefined;
  warningCount: number;
  path?: string | null;
  timings?: Record<string, number> | null;
}

function formatTimings(timings: Record<string, number> | null | undefined): string | null {
  if (!timings || typeof timings !== "object") {
    return null;
  }
  const keys = ["intent_ms", "context_ms", "llm_ms", "sql_ms", "present_ms", "total_ms"];
  const parts = keys
    .map((k) => (typeof timings[k] === "number" ? `${k.replace("_ms", "")} ${timings[k]}ms` : null))
    .filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export function StatusBadge({
  executionMs,
  confidence,
  warningCount,
  path,
  timings,
}: StatusBadgeProps) {
  const timingTitle = formatTimings(timings);
  return (
    <div className="status-row" aria-label="Response status">
      {path ? (
        <span className="status-badge" title="Response path">
          {path}
        </span>
      ) : null}
      {executionMs != null ? (
        <span className="status-badge status-badge--ok" title="End-to-end request time">
          {executionMs} ms
        </span>
      ) : null}
      {timingTitle ? (
        <span className="status-badge" title={timingTitle}>
          timings
        </span>
      ) : null}
      {confidence != null ? (
        <span className="status-badge" title="Structured-result confidence (heuristic)">
          confidence {(confidence * 100).toFixed(0)}%
        </span>
      ) : null}
      {warningCount > 0 ? (
        <span className="status-badge" title="Warnings from the presentation layer">
          {warningCount} warning{warningCount === 1 ? "" : "s"}
        </span>
      ) : null}
    </div>
  );
}
