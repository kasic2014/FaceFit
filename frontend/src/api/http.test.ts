import { afterEach, describe, expect, it, vi } from "vitest";

const successEnvelope = (data: unknown) => ({
  success: true,
  code: "OK",
  message: "ok",
  requestId: "request-id",
  timestamp: "2026-08-05T00:00:00Z",
  data,
});

describe("requestJson", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends the bearer token and unwraps the documented success envelope", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify(successEnvelope({ sessionId: "session-1" })),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { requestJson } = await import("@/api/http");

    await expect(
      requestJson<{ sessionId: string }>(
        "/api/v1/interview-sessions/session-1",
        { accessToken: "access-token" },
      ),
    ).resolves.toEqual({ sessionId: "session-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/interview-sessions/session-1",
      expect.objectContaining({ credentials: "include" }),
    );
    const requestHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(requestHeaders.get("Authorization")).toBe("Bearer access-token");
    expect(requestHeaders.get("Accept")).toBe("application/json");
  });

  it("preserves the flat API error code and retry instructions", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              success: false,
              code: "QUESTION_GENERATION_FAILED",
              message: "retry later",
              requestId: "request-id",
              timestamp: "2026-08-05T00:00:00Z",
              data: { retryable: true, retryAfterSec: 2 },
            }),
            { status: 503, headers: { "Content-Type": "application/json" } },
          ),
        ),
    );
    const { requestJson } = await import("@/api/http");

    await expect(
      requestJson("/api/v1/interview-sessions/session-1/questions/current"),
    ).rejects.toMatchObject({
      status: 503,
      code: "QUESTION_GENERATION_FAILED",
      payload: { retryable: true, retryAfterSec: 2 },
    });
  });
});
