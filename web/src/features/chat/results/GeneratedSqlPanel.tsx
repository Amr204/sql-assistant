import "./ResultsPanels.css";

interface GeneratedSqlPanelProps {
  sql: string;
}

export function GeneratedSqlPanel({ sql }: GeneratedSqlPanelProps) {
  return (
    <details className="sql-details" open={false}>
      <summary className="sql-summary">Generated SQL</summary>
      <pre className="sql-pre">{sql}</pre>
    </details>
  );
}
