/**
 * Runtime validation for API responses (no Zod — keeps bundle small).
 *
 * Last line of defense before `ResultsTable` renders rows; malformed payloads
 * throw or normalize to empty data instead of crashing the UI.
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
  const rows: Array<Record<string, unknown>> = [];
  for (let i = 0; i < value.rows.length; i++) {
    const row = value.rows[i];
    if (!isRecord(row)) {
      throw new Error(`Invalid response: table.rows[${i}] must be an object`);
    }
    rows.push(row);
  }
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
  if (!Array.isArray(value)) {
    throw new Error("Invalid response: errors must be an array");
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

/** Parse and validate a chat API payload; throws on malformed fields. */
export function validateChatResponse(data: unknown): ChatResponse {
  if (!isRecord(data)) {
    throw new Error("Invalid response: not an object");
  }

  return {
    conversation_id: asStringOrNull(data.conversation_id, "conversation_id"),
    request_id: asString(data.request_id, "request_id"),
    question: asString(data.question, "question"),
    answer: asString(data.answer, "answer"),
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
