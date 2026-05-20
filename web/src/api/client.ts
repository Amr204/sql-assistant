const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export const CHAT_TIMEOUT_MS = 60_000;
export const DEFAULT_TIMEOUT_MS = 10_000;

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
      return validate(payload) as T;
    }
    return payload as T;
  } catch (e) {
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
