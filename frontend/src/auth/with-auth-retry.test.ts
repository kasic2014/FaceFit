import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/http";
import { withAuthRetry } from "@/auth/with-auth-retry";

const apiError = (status: number) => new ApiError({ status, code: "ERR", message: "err", requestId: null, payload: null });

describe("withAuthRetry", () => {
  it("retries once with the refreshed token after a 401 when retry is allowed", async () => {
    const run = vi.fn()
      .mockRejectedValueOnce(apiError(401))
      .mockResolvedValueOnce("ok");
    const refresh = vi.fn().mockResolvedValue({ accessToken: "new-token" });

    await expect(withAuthRetry(true, run, () => "old-token", refresh)).resolves.toBe("ok");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenNthCalledWith(1, "old-token");
    expect(run).toHaveBeenNthCalledWith(2, "new-token");
  });

  it("does not retry when canRetry is false", async () => {
    const run = vi.fn().mockRejectedValue(apiError(401));
    const refresh = vi.fn();

    await expect(withAuthRetry(false, run, () => "token", refresh)).rejects.toThrow();
    expect(refresh).not.toHaveBeenCalled();
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("does not retry non-401 errors", async () => {
    const run = vi.fn().mockRejectedValue(apiError(500));
    const refresh = vi.fn();

    await expect(withAuthRetry(true, run, () => "token", refresh)).rejects.toThrow();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("throws the original error when refresh yields no access token", async () => {
    const originalError = apiError(401);
    const run = vi.fn().mockRejectedValue(originalError);
    const refresh = vi.fn().mockResolvedValue(null);

    await expect(withAuthRetry(true, run, () => "token", refresh)).rejects.toBe(originalError);
    expect(run).toHaveBeenCalledTimes(1);
  });
});
