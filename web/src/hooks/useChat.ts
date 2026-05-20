/**
 * Chat send/clear state with request-generation guards.
 *
 * Prevents stale HTTP responses from updating UI after a newer send or clear.
 * Cancellation (AbortError) is silent; real API errors surface in `error`.
 */
import { useCallback, useRef, useState } from "react";
import { isRequestAborted } from "../api/abort";
import { sendChatMessage } from "../api/chat";
import { ApiError } from "../api/client";
import type { ChatMessage } from "../api/types";
import { ui } from "../locale/uiStrings";
import { usePersistedChat } from "./usePersistedChat";

function mapResponseToMessage(res: Awaited<ReturnType<typeof sendChatMessage>>): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: res.answer || ui.noReply,
    timestamp: Date.now(),
    sql: res.sql,
    table: res.table,
    explanation: res.explanation ?? undefined,
    confidence: res.confidence ?? undefined,
    execution_ms: res.execution_ms ?? undefined,
    warnings: res.warnings,
    path: res.path ?? undefined,
    timings: res.timings ?? undefined,
  };
}

/** Chat state: persisted messages, send/clear, busy flag, and last error. */
export function useChat() {
  const [messages, setMessages] = usePersistedChat();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const requestGenRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) {
        return;
      }

      const gen = ++requestGenRef.current;
      activeControllerRef.current?.abort();
      const controller = new AbortController();
      activeControllerRef.current = controller;

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: q,
        timestamp: Date.now(),
      };
      setMessages((m) => [...m, userMsg]);
      setBusy(true);
      setError(null);

      try {
        const res = await sendChatMessage(
          {
            question: q,
            conversation_id: conversationId,
          },
          { signal: controller.signal },
        );
        if (gen !== requestGenRef.current) {
          return;
        }
        setConversationId(res.conversation_id);
        setMessages((m) => [...m, mapResponseToMessage(res)]);
      } catch (e) {
        if (isRequestAborted(e) || gen !== requestGenRef.current) {
          return;
        }
        const msg =
          e instanceof ApiError
            ? typeof e.payload === "object" && e.payload && "detail" in (e.payload as object)
              ? JSON.stringify((e.payload as { detail: unknown }).detail)
              : e.message
            : ui.requestFailed;
        setError(msg);
      } finally {
        if (gen === requestGenRef.current) {
          setBusy(false);
          if (activeControllerRef.current === controller) {
            activeControllerRef.current = null;
          }
        }
      }
    },
    [busy, conversationId, setMessages],
  );

  const clear = useCallback(() => {
    requestGenRef.current += 1;
    activeControllerRef.current?.abort();
    activeControllerRef.current = null;
    setBusy(false);
    setMessages([]);
    setConversationId(null);
    setError(null);
  }, [setMessages]);

  return { messages, busy, error, send, clear, conversationId };
}
