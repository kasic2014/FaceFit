import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/http";
import { createIdempotencyKey, poll } from "@/api/polling";

describe("poll", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("uses the server retry delay before requesting a processing resource again", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", { clearTimeout, setTimeout });
    const load = vi
      .fn()
      .mockResolvedValueOnce({ status: "PROCESSING", retryAfterSec: 2 })
      .mockResolvedValueOnce({ status: "READY", retryAfterSec: 0 });

    const result = poll<{ status: "PROCESSING" | "READY"; retryAfterSec: number }>({
      load,
      shouldContinue: (value) => value.status === "PROCESSING",
      retryAfterMs: (value) => value.retryAfterSec * 1000,
      intervalMs: 100,
      maxWaitMs: 10_000,
    });
    await vi.runAllTimersAsync();

    await expect(result).resolves.toEqual({
      status: "READY",
      retryAfterSec: 0,
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("retries an explicitly retryable API failure and then returns the resource", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", { clearTimeout, setTimeout });
    const retryableError = new ApiError({
      status: 503,
      code: "TEMPORARY_UNAVAILABLE",
      message: "retry",
      requestId: null,
      payload: { retryAfterSec: 1 },
    });
    const load = vi
      .fn()
      .mockRejectedValueOnce(retryableError)
      .mockResolvedValueOnce({ status: "READY" });

    const result = poll({
      load,
      shouldContinue: () => false,
      intervalMs: 100,
      maxWaitMs: 10_000,
    });
    await vi.runAllTimersAsync();

    await expect(result).resolves.toEqual({ status: "READY" });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("generates UUID idempotency keys for mutation requests", () => {
    expect(createIdempotencyKey()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });
});
