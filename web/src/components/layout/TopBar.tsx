import "./TopBar.css";
import { StatusPill } from "../../features/diagnostics/StatusPill";
import type { StatusResponse } from "../../api/types";

interface TopBarProps {
  status: StatusResponse | null;
  statusError: string | null;
}

export function TopBar({ status, statusError }: TopBarProps) {
  return (
    <div className="topbar-row">
      <div className="topbar-title">Ask your database</div>
      <div className="topbar-actions">
        <StatusPill status={status} error={statusError} />
      </div>
    </div>
  );
}
