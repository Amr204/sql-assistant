import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CodeBlock } from "./CodeBlock";
import { sanitizePrismHtml } from "./sanitizePrismHtml";

afterEach(() => {
  cleanup();
});

describe("sanitizePrismHtml", () => {
  it("removes script tags and event handlers", () => {
    const dirty = '<span class="token">x</span><script>alert(1)</script><img onerror="alert(2)">';
    const clean = sanitizePrismHtml(dirty);
    expect(clean).not.toContain("<script");
    expect(clean).not.toContain("onerror");
  });
});

describe("CodeBlock", () => {
  it("does not leave executable script markup in highlighted output", () => {
    const { container } = render(
      <CodeBlock code={'SELECT 1; </script><script>alert("xss")</script>'} />,
    );
    const html = container.querySelector("code")?.innerHTML ?? "";
    expect(html.toLowerCase()).not.toContain("<script");
  });
});
