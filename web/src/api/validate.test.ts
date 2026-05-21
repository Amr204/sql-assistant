import { describe, expect, it } from "vitest";
import { isAcceptableChatResponse, normalizeSqlTable, validateChatResponse } from "./validate";

describe("validateChatResponse", () => {
  it("parses a full structured response", () => {
    const res = validateChatResponse({
      conversation_id: "c1",
      request_id: "r1",
      question: "q",
      answer: "a",
      sql: "SELECT 1",
      table: {
        columns: ["x"],
        rows: [{ x: 1 }],
        row_count: 1,
        truncated: false,
      },
      warnings: [],
      errors: [],
      execution_ms: 10,
    });
    expect(res.table?.columns).toEqual(["x"]);
    expect(res.table?.rows[0]).toEqual({ x: 1 });
  });

  it("accepts missing answer when table is present", () => {
    const res = validateChatResponse({
      request_id: "r1",
      question: "q",
      answer: "",
      sql: "SELECT 1",
      table: {
        columns: ["x"],
        rows: [{ x: 1 }],
        row_count: 1,
        truncated: false,
      },
      warnings: [],
      errors: [],
    });
    expect(isAcceptableChatResponse(res)).toBe(true);
  });

  it("treats errors object as empty", () => {
    const res = validateChatResponse({
      conversation_id: "c1",
      request_id: "r1",
      question: "q",
      answer: "ok",
      warnings: [],
      errors: {},
      execution_ms: 1,
    });
    expect(res.errors).toEqual([]);
    expect(isAcceptableChatResponse(res)).toBe(true);
  });

  it("rejects generic tool-only answer without table", () => {
    const res = validateChatResponse({
      request_id: "r1",
      question: "q",
      answer: "Tool completed successfully",
      warnings: [],
      errors: [],
      path: "vanna_agent",
    });
    expect(isAcceptableChatResponse(res)).toBe(false);
  });

  it("accepts answer with table even when errors empty object", () => {
    const res = validateChatResponse({
      request_id: "r1",
      question: "q",
      answer: "تم إرجاع 5 سجلًا.",
      sql: "SELECT TOP 5 * FROM dbo.Customers",
      table: {
        columns: ["id"],
        rows: [{ id: 1 }],
        row_count: 1,
        truncated: false,
      },
      warnings: [],
      errors: {},
      path: "sql_fast",
    });
    expect(isAcceptableChatResponse(res)).toBe(true);
  });

  it("parses table rows as arrays", () => {
    const res = validateChatResponse({
      request_id: "r1",
      question: "q",
      answer: "a",
      table: {
        columns: ["a", "b"],
        rows: [[1, "x"]],
        row_count: 1,
        truncated: false,
      },
      warnings: [],
      errors: [],
    });
    expect(res.table?.rows[0]).toEqual({ a: 1, b: "x" });
  });
});

describe("normalizeSqlTable", () => {
  it("returns null for malformed table without throwing", () => {
    expect(normalizeSqlTable({ columns: "bad", rows: [] } as never)).toBeNull();
  });
});
