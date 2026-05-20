/** POST /api/v1/chat — validated response via `validateChatResponse`. */
import { apiRequest, CHAT_TIMEOUT_MS } from "./client";
import type { ChatRequest, ChatResponse } from "./types";
import { validateChatResponse } from "./validate";

export type SendChatOptions = {
  signal?: AbortSignal;
};

/** Send a chat question; honours `signal` for cancellation. */
export async function sendChatMessage(
  payload: ChatRequest,
  options: SendChatOptions = {},
): Promise<ChatResponse> {
  return apiRequest<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options.signal,
    timeoutMs: CHAT_TIMEOUT_MS,
    validate: validateChatResponse,
  });
}
