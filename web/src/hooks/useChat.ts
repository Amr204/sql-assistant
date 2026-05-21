/**
 * Chat send/clear state with request-generation guards.
 *
 * Prevents stale HTTP responses from updating UI after a newer send or clear.
 * Cancellation (AbortError) is silent; real API errors surface in `error` and chat.
 */
import { useCallback, useRef, useState } from "react";
import { isRequestAborted } from "../api/abort";
import { sendChatMessage } from "../api/chat";
import { ApiError } from "../api/client";
import type { ChatMessage, ChatResponse } from "../api/types";
import {
  hasDisplayableResults,
  isAcceptableChatResponse,
  validateChatResponse,
} from "../api/validate";
import { formatChatError } from "../lib/formatApiError";
import { ui } from "../locale/uiStrings";
import { usePersistedChat } from "./usePersistedChat";

function mapResponseToMessage(res: ChatResponse): ChatMessage {
  const content =
    res.answer?.trim() ||
    (res.table && res.table.row_count > 0
      ? `تم إرجاع ${res.table.row_count} سجلًا.`
      : ui.noReply);

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content,
    timestamp: Date.now(),
    sql: res.sql,
    table: res.table,
    explanation: res.explanation ?? undefined,
    confidence: res.confidence ?? undefined,
    execution_ms: res.execution_ms ?? undefined,
    warnings: res.warnings,
    path: res.path ?? undefined,
    timings: res.timings ?? undefined,
    apiErrors: res.errors.length > 0 ? res.errors : undefined,
  };
}

function assistantErrorMessage(text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: text,
    timestamp: Date.now(),
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

      console.debug("[chat] send", { question: q, conversationId, gen });
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

        console.debug("[chat] response", {
          aborted: controller.signal.aborted,
          gen,
          answer: res.answer?.slice(0, 120),
          sql: res.sql?.slice(0, 80),
          tableRows: res.table?.rows?.length,
          tableColumns: res.table?.columns,
          errors: res.errors,
          path: res.path,
        });

        if (controller.signal.aborted) {
          console.debug("[chat] skip stale response (aborted)", { gen });
          return;
        }

        if (!isAcceptableChatResponse(res)) {
          const apiErr =
            res.errors[0]?.message ||
            "لم يُرجع الخادم إجابة أو جدولًا صالحًا.";
          console.debug("[chat] response not acceptable", res);
          setError(apiErr);
          setMessages((m) => [...m, assistantErrorMessage(apiErr)]);
          return;
        }

        if (res.conversation_id) {
          setConversationId(res.conversation_id);
        }

        const assistantMsg = mapResponseToMessage(res);
        console.debug("[chat] append assistant", {
          content: assistantMsg.content?.slice(0, 120),
          hasTable: Boolean(assistantMsg.table),
          rowCount: assistantMsg.table?.row_count,
          tableRows: assistantMsg.table?.rows?.length,
          displayable: hasDisplayableResults(assistantMsg),
          path: assistantMsg.path,
        });
        setMessages((m) => [...m, assistantMsg]);
      } catch (e) {
        if (isRequestAborted(e) || controller.signal.aborted) {
          console.debug("[chat] request aborted", { gen });
          return;
        }

        let res: ChatResponse | null = null;
        if (e instanceof ApiError && e.payload) {
          try {
            res = validateChatResponse(e.payload);
            if (isAcceptableChatResponse(res)) {
              console.debug("[chat] recovered from validation error via raw payload", res);
              if (res.conversation_id) {
                setConversationId(res.conversation_id);
              }
              setMessages((m) => [...m, mapResponseToMessage(res!)]);
              return;
            }
          } catch {
            /* use formatted error below */
          }
        }

        const msg = formatChatError(e, ui.requestFailed);
        console.debug("[chat] error", { gen, msg, error: e });
        setError(msg);
        setMessages((m) => [...m, assistantErrorMessage(msg)]);
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
