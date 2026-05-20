import { ApiError } from "../api/client";

function isRetryableError(error: unknown): boolean {
  if (error instanceof TypeError) {
    return true;
  }
  if (error instanceof ApiError) {
    return error.status === 0 || error.status >= 500;
  }
  return false;
}

export type StartupRetryOptions = {
  attempts?: number;
  delayMs?: number;
};

/** Retry while the API is still starting (dev proxy ECONNREFUSED, 502, etc.). */
export async function withStartupRetry<T>(
  fn: () => Promise<T>,
  options: StartupRetryOptions = {},
): Promise<T> {
  const { attempts = 60, delayMs = 1000 } = options;
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (e) {
      last = e;
      if (!isRetryableError(e) || i === attempts - 1) {
        throw e;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw last;
}
