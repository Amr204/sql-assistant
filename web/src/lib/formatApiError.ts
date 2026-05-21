/** Turn FastAPI / fetch error payloads into user-visible chat text. */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function formatApiErrorPayload(payload: unknown, fallback: string): string {
  if (payload == null) {
    return fallback;
  }
  if (typeof payload === "string") {
    return payload;
  }
  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (isRecord(detail)) {
    const message = detail.message;
    const code = detail.code;
    if (typeof message === "string" && message.trim()) {
      return typeof code === "string" && code.trim()
        ? `${code}: ${message}`
        : message;
    }
    if (typeof code === "string" && code.trim()) {
      return code;
    }
  }

  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }

  try {
    return JSON.stringify(payload);
  } catch {
    return fallback;
  }
}

export function formatChatError(error: unknown, fallback: string): string {
  if (
    error instanceof Error &&
    error.name === "ApiError" &&
    "payload" in error
  ) {
    return formatApiErrorPayload(
      (error as Error & { payload?: unknown }).payload,
      error.message || fallback,
    );
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}
