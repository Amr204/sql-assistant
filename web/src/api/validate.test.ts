import { describe, expect, it } from "vitest";
import { normalizeSqlTable, validateChatResponse } from "./validate";

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

  it("rejects missing answer", () => {
    expect(() =>
      validateChatResponse({
        request_id: "r1",
        question: "q",
        warnings: [],
        errors: [],
      }),
    ).toThrow(/answer/);
  });
});

describe("normalizeSqlTable", () => {
  it("returns null for malformed table without throwing", () => {
    expect(normalizeSqlTable({ columns: "bad", rows: [] } as never)).toBeNull();
  });
});
