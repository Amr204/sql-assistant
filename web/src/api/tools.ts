import { apiRequest } from "./client";
import type { ToolsListResponse } from "./types";

export function fetchTools(): Promise<ToolsListResponse> {
  return apiRequest<ToolsListResponse>("/api/v1/tools");
}
