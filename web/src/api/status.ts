import { apiRequest } from "./client";
import type { StatusResponse } from "./types";

export function fetchStatus(): Promise<StatusResponse> {
  return apiRequest<StatusResponse>("/api/v1/status");
}
