import { memo } from "react";
import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";
import type { StatusResponse } from "../../api/types";
import { ui } from "../../locale/uiStrings";

interface StatusPillProps {
  status: StatusResponse | null;
  error: string | null;
}

export const StatusPill = memo(function StatusPill({ status, error }: StatusPillProps) {
  if (error) {
    return (
      <Badge tone="err" title={error}>
        {ui.agentStatus}: {ui.agentError}
      </Badge>
    );
  }
  if (!status) {
    return (
      <Badge>
        <span className="status-pill-loading">
          <Spinner />
          {ui.agentStatus}: {ui.agentLoading}
        </span>
      </Badge>
    );
  }
  const tone = status.status === "ok" ? "ok" : "warn";
  return (
    <Badge tone={tone}>
      {ui.agentStatus}: {status.status === "ok" ? ui.agentReady : ui.agentDegraded}
    </Badge>
  );
});
