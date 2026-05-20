import { apiRequest } from "./client";
import type { StatusResponse } from "./types";

/** Readiness and health flags from GET /api/v1/status. */
export function fetchStatus(): Promise<StatusResponse> {
  return apiRequest<StatusResponse>("/api/v1/status");
}
