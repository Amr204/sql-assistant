import type { StatusResponse } from "../../api/types";
import { StatusPill } from "../../features/diagnostics/StatusPill";
import { ThemeToggle } from "../../features/diagnostics/ThemeToggle";
import { ui } from "../../locale/uiStrings";
import "./TopBar.css";

interface TopBarProps {
  status: StatusResponse | null;
  statusError: string | null;
}

export function TopBar({ status, statusError }: TopBarProps) {
  return (
    <div className="topbar-row">
      <div className="topbar-title">{ui.topBarTitle}</div>
      <div className="topbar-actions">
        <ThemeToggle />
        <StatusPill status={status} error={statusError} />
      </div>
    </div>
  );
}
