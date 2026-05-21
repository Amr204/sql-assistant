/**
 * HTTP client for the FastAPI backend.
 *
 * Boundary: transport only (timeouts, abort, JSON parse). Response shape validation
 * lives in `validate.ts`. Aborted fetches propagate as `AbortError` (not user errors).
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export const CHAT_TIMEOUT_MS = 60_000;
export const DEFAULT_TIMEOUT_MS = 10_000;

/** HTTP error with status code and parsed JSON body (if any). */
export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export { formatApiErrorPayload } from "../lib/formatApiError";

function linkAbort(target: AbortController, source: AbortSignal): void {
  if (source.aborted) {
    target.abort();
    return;
  }
  source.addEventListener("abort", () => target.abort(), { once: true });
}

function mergeSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  const merged = new AbortController();
  linkAbort(merged, a);
  linkAbort(merged, b);
  return merged.signal;
}

export type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
  validate?: (data: unknown) => unknown;
};

/**
 * Fetch JSON from the API with timeout and optional `validate` callback.
 * Aborts propagate as `AbortError`; does not swallow user cancellation.
 */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, validate, signal: userSignal, ...fetchOptions } = options;
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  const signal = userSignal
    ? mergeSignals(userSignal, timeoutController.signal)
    : timeoutController.signal;

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchOptions,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchOptions.headers ?? {}),
      },
    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      throw new ApiError(`API request failed: ${response.status}`, response.status, payload);
    }

    if (validate) {
      try {
        return validate(payload) as T;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Invalid response";
        throw new ApiError(msg, response.status, payload);
      }
    }
    return payload as T;
  } finally {
    clearTimeout(timer);
  }
}
