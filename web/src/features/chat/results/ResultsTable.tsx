import type { SqlTable } from "../../../api/types";
import "./ResultsPanels.css";

interface ResultsTableProps {
  table: SqlTable;
}

export function ResultsTable({ table }: ResultsTableProps) {
  const cols = table.columns.filter((c) => c !== "__proto__");
  if (cols.length === 0) {
    return null;
  }
  return (
    <section className="result-card" aria-label="Query results">
      <h3 className="result-card-title">Query results</h3>
      <p className="result-card-title" style={{ textTransform: "none", letterSpacing: 0, marginBottom: 8 }}>
        {table.row_count} row{table.row_count === 1 ? "" : "s"}
        {table.truncated ? " (truncated)" : ""}
      </p>
      <div className="table-wrap" role="region">
        <table className="data-table">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c}>{String(row[c] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
