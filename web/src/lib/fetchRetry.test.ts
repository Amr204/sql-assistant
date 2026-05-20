import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { withStartupRetry } from "./fetchRetry";

describe("withStartupRetry", () => {
  it("retries retryable errors then succeeds", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce("ok");

    await expect(withStartupRetry(fn, { attempts: 3, delayMs: 1 })).resolves.toBe("ok");
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("does not retry client errors", async () => {
    const fn = vi.fn().mockRejectedValue(new ApiError("bad", 400, null));
    await expect(withStartupRetry(fn, { attempts: 3, delayMs: 1 })).rejects.toBeInstanceOf(ApiError);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
