import { memo } from "react";
import { CodeBlock } from "../../../components/CodeBlock";
import { ui } from "../../../locale/uiStrings";
import "./ResultsPanels.css";

interface GeneratedSqlPanelProps {
  sql: string;
}

export const GeneratedSqlPanel = memo(function GeneratedSqlPanel({ sql }: GeneratedSqlPanelProps) {
  return (
    <details className="sql-details" open={false}>
      <summary className="sql-summary">{ui.generatedSql}</summary>
      <CodeBlock code={sql} language="sql" />
    </details>
  );
});
