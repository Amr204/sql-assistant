import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { ChatMessage, SqlTable } from "../api/types";

const STORAGE_KEY = "sql-assistant-messages";
const STORAGE_VERSION = 2;
const MAX_MESSAGES = 50;
const TTL_MS = 7 * 24 * 60 * 60 * 1000;

type StoredTableMeta = {
  columns: string[];
  row_count: number;
  truncated: boolean;
};

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  sql?: string | null;
  table?: StoredTableMeta | null;
  explanation?: string | null;
  confidence?: number | null;
  execution_ms?: number | null;
  warnings?: string[];
  path?: string | null;
  timings?: Record<string, number> | null;
};

type StoredPayload = {
  version: number;
  savedAt: number;
  messages: StoredMessage[];
};

function toStored(msg: ChatMessage): StoredMessage {
  const table = msg.table;
  const storedTable: StoredTableMeta | null | undefined = table
    ? {
        columns: table.columns,
        row_count: table.row_count,
        truncated: table.truncated,
      }
    : table;

  return {
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp ?? Date.now(),
    sql: msg.sql,
    table: storedTable,
    explanation: msg.explanation,
    confidence: msg.confidence,
    execution_ms: msg.execution_ms,
    warnings: msg.warnings,
    path: msg.path,
    timings: msg.timings,
  };
}

function fromStored(msg: StoredMessage): ChatMessage {
  const meta = msg.table;
  const table: SqlTable | null | undefined = meta
    ? {
        columns: meta.columns,
        rows: [],
        row_count: meta.row_count,
        truncated: meta.truncated,
      }
    : meta;

  return {
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp,
    sql: msg.sql,
    table,
    explanation: msg.explanation,
    confidence: msg.confidence,
    execution_ms: msg.execution_ms,
    warnings: msg.warnings,
    path: msg.path,
    timings: msg.timings,
  };
}

function trimMessages(messages: StoredMessage[]): StoredMessage[] {
  const now = Date.now();
  const fresh = messages.filter((m) => now - (m.timestamp ?? 0) <= TTL_MS);
  return fresh.slice(-MAX_MESSAGES);
}

function loadMessages(): ChatMessage[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) {
      return [];
    }
    const parsed = JSON.parse(saved) as StoredPayload | StoredMessage[];
    if (Array.isArray(parsed)) {
      return trimMessages(parsed as StoredMessage[]).map(fromStored);
    }
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      Array.isArray((parsed as StoredPayload).messages)
    ) {
      const payload = parsed as StoredPayload;
      if (Date.now() - payload.savedAt > TTL_MS) {
        return [];
      }
      return trimMessages(payload.messages).map(fromStored);
    }
    return [];
  } catch {
    return [];
  }
}

function persist(messages: ChatMessage[]): void {
  const stored = trimMessages(messages.map(toStored));
  const payload: StoredPayload = {
    version: STORAGE_VERSION,
    savedAt: Date.now(),
    messages: stored,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function usePersistedChat(): readonly [ChatMessage[], Dispatch<SetStateAction<ChatMessage[]>>] {
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);

  useEffect(() => {
    persist(messages);
  }, [messages]);

  return [messages, setMessages] as const;
}
