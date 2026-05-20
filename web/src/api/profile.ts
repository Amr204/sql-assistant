import { apiRequest } from "./client";
import type { ProfileResponse } from "./types";

/** Load active database profile metadata from GET /api/v1/profile. */
export function fetchProfile(): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>("/api/v1/profile");
}
