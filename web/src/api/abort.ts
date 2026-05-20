import { ApiError } from "./client";

/** True when the user or a newer request cancelled this fetch. */
export function isRequestAborted(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") {
    return true;
  }
  if (error instanceof ApiError && error.status === 0 && error.message === "Request aborted") {
    return true;
  }
  return false;
}
