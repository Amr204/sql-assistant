import { Card } from "../../components/ui/Card";
import type { StatusResponse } from "../../api/types";

interface ReadinessPanelProps {
  status: StatusResponse | null;
}

export function ReadinessPanel({ status }: ReadinessPanelProps) {
  if (!status) {
    return null;
  }
  const rows: Array<{ label: string; ok: boolean }> = [
    { label: "Profile", ok: status.profile_ready },
    { label: "Agent", ok: status.agent_ready },
    { label: "Memory", ok: status.memory_ready },
    { label: "Tools", ok: status.tools_ready },
    { label: "LLM", ok: status.llm_ready },
  ];
  return (
    <Card>
      <h3 style={{ fontSize: 17 }}>Diagnostics</h3>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((r) => (
          <li
            key={r.label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "8px 0",
              borderBottom: "1px solid var(--color-border)",
              fontSize: 14,
            }}
          >
            <span>{r.label}</span>
            <span style={{ color: r.ok ? "var(--color-success)" : "var(--color-danger)" }}>
              {r.ok ? "yes" : "no"}
            </span>
          </li>
        ))}
      </ul>
      {status.errors.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 13, color: "var(--color-muted)" }}>
          {status.errors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}
    </Card>
  );
}
