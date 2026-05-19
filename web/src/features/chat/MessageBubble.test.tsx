import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MessageBubble } from "./MessageBubble";

afterEach(() => {
  cleanup();
});

describe("MessageBubble", () => {
  it("renders structured table when table is present", () => {
    render(
      <MessageBubble
        message={{
          id: "1",
          role: "assistant",
          content: "تم إرجاع 2 سجلًا.",
          sql: "SELECT TOP 2 CustomerID, CompanyName FROM dbo.Customers",
          table: {
            columns: ["CustomerID", "CompanyName"],
            rows: [
              { CustomerID: 1, CompanyName: "A" },
              { CustomerID: 2, CompanyName: "B" },
            ],
            row_count: 2,
            truncated: false,
          },
          explanation: "تم تنفيذ الاستعلام بنجاح.",
          execution_ms: 42,
          confidence: 0.92,
          warnings: [],
        }}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "CustomerID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "CompanyName" })).toBeInTheDocument();
    expect(screen.getByText("تم إرجاع 2 سجلًا.")).toBeInTheDocument();
  });

  it("shows Generated SQL panel when sql is set", () => {
    render(
      <MessageBubble
        message={{
          id: "2",
          role: "assistant",
          content: "عدد السجلات في جدول Suppliers هو 29 سجلًا.",
          sql: "SELECT COUNT(*) AS [record_count] FROM dbo.Suppliers",
          explanation: "تم تنفيذ استعلام عدّ مباشر على الجدول المطلوب.",
          execution_ms: 10,
          confidence: 0.95,
        }}
      />,
    );
    expect(screen.getByText("Generated SQL")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader")).not.toBeInTheDocument();
  });

  it("does not surface CSV filenames in summary", () => {
    render(
      <MessageBubble
        message={{
          id: "3",
          role: "assistant",
          content: "A clean summary only.",
        }}
      />,
    );
    expect(screen.queryByText(/query_results_/i)).not.toBeInTheDocument();
  });
});
