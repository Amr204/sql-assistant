import { apiRequest } from "./client";
import type { ProfileResponse } from "./types";

export function fetchProfile(): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>("/api/v1/profile");
}
