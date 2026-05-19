import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";
import type { StatusResponse } from "../../api/types";

interface StatusPillProps {
  status: StatusResponse | null;
  error: string | null;
}

export function StatusPill({ status, error }: StatusPillProps) {
  if (error) {
    return (
      <Badge tone="err" title={error}>
        Agent Status: error
      </Badge>
    );
  }
  if (!status) {
    return (
      <Badge>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Spinner />
          Agent Status: loading
        </span>
      </Badge>
    );
  }
  const tone = status.status === "ok" ? "ok" : "warn";
  return (
    <Badge tone={tone}>
      Agent Status: {status.status === "ok" ? "ready" : "degraded"}
    </Badge>
  );
}
