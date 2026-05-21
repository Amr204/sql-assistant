/**
 * Runtime validation for API responses (no Zod — keeps bundle small).
 *
 * Last line of defense before `ResultsTable` renders rows; malformed payloads
 * normalize when possible instead of crashing the UI.
 */
import type { ChatResponse, SqlTable } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`Invalid response: ${field} must be a string`);
  }
  return value;
}

function asStringOrNull(value: unknown, field: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return asString(value, field);
}

function asNumberOrNull(value: unknown, field: string): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`Invalid response: ${field} must be a number`);
  }
  return value;
}

function asStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`Invalid response: ${field} must be an array`);
  }
  return value.map((item, i) => asString(item, `${field}[${i}]`));
}

function parseRow(
  row: unknown,
  columns: string[],
  index: number,
): Record<string, unknown> {
  if (isRecord(row)) {
    return row;
  }
  if (Array.isArray(row)) {
    const out: Record<string, unknown> = {};
    for (let i = 0; i < columns.length; i++) {
      out[columns[i]] = row[i] ?? null;
    }
    return out;
  }
  throw new Error(`Invalid response: table.rows[${index}] must be an object or array`);
}

function parseSqlTable(value: unknown): SqlTable | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Invalid response: table must be an object");
  }
  const columns = asStringArray(value.columns, "table.columns");
  if (!Array.isArray(value.rows)) {
    throw new Error("Invalid response: table.rows must be an array");
  }
  const rows = value.rows.map((row, i) => parseRow(row, columns, i));
  const rowCountRaw = value.row_count;
  const row_count =
    typeof rowCountRaw === "number" && !Number.isNaN(rowCountRaw)
      ? rowCountRaw
      : rows.length;
  return {
    columns,
    rows,
    row_count,
    truncated: value.truncated === true,
  };
}

function parseApiErrors(value: unknown): ChatResponse["errors"] {
  if (value === null || value === undefined) {
    return [];
  }
  if (isRecord(value) && Object.keys(value).length === 0) {
    return [];
  }
  if (!Array.isArray(value)) {
    if (isRecord(value) && typeof value.message === "string") {
      return [
        {
          code: typeof value.code === "string" ? value.code : "API_ERROR",
          message: value.message,
          details: isRecord(value.details) ? value.details : {},
        },
      ];
    }
    return [];
  }
  return value.map((item, i) => {
    if (!isRecord(item)) {
      throw new Error(`Invalid response: errors[${i}] must be an object`);
    }
    const details = item.details;
    return {
      code: asString(item.code, `errors[${i}].code`),
      message: asString(item.message, `errors[${i}].message`),
      details: isRecord(details) ? details : {},
    };
  });
}

function parseTimings(value: unknown): Record<string, number> | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isRecord(value)) {
    return null;
  }
  const out: Record<string, number> = {};
  for (const [key, v] of Object.entries(value)) {
    if (typeof v === "number" && !Number.isNaN(v)) {
      out[key] = v;
    }
  }
  return Object.keys(out).length > 0 ? out : null;
}

const GENERIC_ANSWER_RE =
  /tool\s+completed|completed\s+successfully|no text reply|لم يُنفَّذ استعلام sql/i;

function hasStructuredData(res: ChatResponse): boolean {
  if (res.sql?.trim()) {
    return true;
  }
  if (res.errors?.length && res.answer?.trim()) {
    return true;
  }
  const table = res.table;
  return Boolean(
    table &&
      table.columns.length > 0 &&
      (table.rows.length > 0 || (table.row_count ?? 0) > 0),
  );
}

function isMeaningfulAnswer(answer: string): boolean {
  const text = answer.trim();
  if (!text) {
    return false;
  }
  return !GENERIC_ANSWER_RE.test(text);
}

/** True when the payload has enough content to show in the UI. */
export function isAcceptableChatResponse(res: ChatResponse): boolean {
  if (hasStructuredData(res)) {
    return true;
  }
  return isMeaningfulAnswer(res.answer ?? "");
}

export function hasDisplayableResults(message: {
  sql?: string | null;
  table?: SqlTable | null;
  content: string;
}): boolean {
  if (message.sql?.trim()) {
    return true;
  }
  const table = message.table;
  if (table && table.columns.length > 0 && table.rows.length > 0) {
    return true;
  }
  return isMeaningfulAnswer(message.content);
}

/** Best-effort re-parse of a table; returns null on invalid shape. */
export function normalizeSqlTable(table: SqlTable | null | undefined): SqlTable | null {
  if (!table) {
    return null;
  }
  try {
    return parseSqlTable(table);
  } catch {
    return null;
  }
}

/** Parse and validate a chat API payload; throws only on unusable shapes. */
export function validateChatResponse(data: unknown): ChatResponse {
  if (!isRecord(data)) {
    throw new Error("Invalid response: not an object");
  }

  const answerRaw = data.answer;
  const answer =
    typeof answerRaw === "string"
      ? answerRaw
      : answerRaw === null || answerRaw === undefined
        ? ""
        : (() => {
            throw new Error("Invalid response: answer must be a string");
          })();

  return {
    conversation_id: asStringOrNull(data.conversation_id, "conversation_id"),
    request_id: asString(data.request_id, "request_id"),
    question: asString(data.question, "question"),
    answer,
    sql: asStringOrNull(data.sql, "sql"),
    explanation: asStringOrNull(data.explanation, "explanation"),
    confidence: asNumberOrNull(data.confidence, "confidence"),
    table: parseSqlTable(data.table),
    warnings: Array.isArray(data.warnings)
      ? data.warnings.map((w, i) => asString(w, `warnings[${i}]`))
      : [],
    errors: parseApiErrors(data.errors),
    execution_ms:
      data.execution_ms === null || data.execution_ms === undefined
        ? null
        : asNumberOrNull(data.execution_ms, "execution_ms"),
    path: asStringOrNull(data.path, "path"),
    timings: parseTimings(data.timings),
  };
}
