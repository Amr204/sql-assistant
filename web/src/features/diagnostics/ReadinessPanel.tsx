import { useMemo } from "react";
import { Card } from "../../components/ui/Card";
import type { StatusResponse } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import "./ReadinessPanel.css";

interface ReadinessPanelProps {
  status: StatusResponse | null;
}

export function ReadinessPanel({ status }: ReadinessPanelProps) {
  const rows = useMemo(() => {
    if (!status) {
      return [];
    }
    return [
      { label: ui.profile, ok: status.profile_ready },
      { label: "Agent", ok: status.agent_ready },
      { label: "Memory", ok: status.memory_ready },
      { label: ui.tools, ok: status.tools_ready },
      { label: "LLM", ok: status.llm_ready },
    ];
  }, [status]);

  if (!status) {
    return null;
  }

  return (
    <Card>
      <h3 className="section-title">{ui.diagnostics}</h3>
      <ul className="readiness-list">
        {rows.map((r) => (
          <li key={r.label} className="readiness-row">
            <span>{r.label}</span>
            <span className={r.ok ? "readiness-ok" : "readiness-bad"}>
              {r.ok ? ui.yes : ui.no}
            </span>
          </li>
        ))}
      </ul>
      {status.errors.length > 0 && (
        <div className="readiness-errors">
          {status.errors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}
    </Card>
  );
}
