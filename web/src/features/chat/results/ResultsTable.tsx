import { memo, useMemo } from "react";
import type { SqlTable } from "../../../api/types";
import { normalizeSqlTable } from "../../../api/validate";
import { exportResultsCsv } from "../../../lib/exportCsv";
import { ui } from "../../../locale/uiStrings";
import "./ResultsPanels.css";

interface ResultsTableProps {
  table: SqlTable;
}

const MAX_RENDER_ROWS = 500;

export const ResultsTable = memo(function ResultsTable({ table }: ResultsTableProps) {
  const safe = useMemo(() => normalizeSqlTable(table), [table]);

  const cols = useMemo(
    () => (safe?.columns ?? []).filter((c) => c !== "__proto__" && typeof c === "string"),
    [safe?.columns],
  );

  const rows = useMemo(() => {
    if (!safe?.rows) {
      return [];
    }
    return safe.rows.slice(0, MAX_RENDER_ROWS);
  }, [safe?.rows]);

  if (!safe || cols.length === 0) {
    return <p className="text-muted">{ui.noData}</p>;
  }

  return (
    <section className="result-card" aria-label={ui.queryResults}>
      <div className="result-card-header">
        <h3 className="result-card-title">{ui.queryResults}</h3>
        <button
          type="button"
          className="export-btn"
          onClick={() => exportResultsCsv(cols, safe.rows)}
        >
          {ui.exportCsv}
        </button>
      </div>
      <p className="result-meta">
        {safe.row_count} {ui.rows}
        {safe.truncated ? ` ${ui.truncated}` : ""}
        {safe.rows.length > MAX_RENDER_ROWS ? ` (${ui.tablePreviewLimited})` : ""}
      </p>
      <div className="table-wrap" role="region" tabIndex={0}>
        <table className="data-table">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c}>{formatCell(row[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
});

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }
  return String(value);
}
