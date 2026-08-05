import { afterEach, describe, expect, it, vi } from "vitest";

const authEnvelope = (data: unknown) => ({
  success: true,
  code: "OK",
  message: "ok",
  requestId: "request-id",
  timestamp: "2026-08-05T00:00:00Z",
  data,
});

const authData = {
  authenticated: true,
  accessToken: "access-token",
  accessTokenExpiresInSec: 3600,
  nextAction: "GO_TO_SERVICE",
};

function stubFetchOk() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(authEnvelope(authData)), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("auth api", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends token refresh as POST", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    const fetchMock = stubFetchOk();
    const { refreshAuthSession } = await import("@/api/auth");

    await refreshAuthSession();

    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("sends the login ticket as a JSON POST body", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    const fetchMock = stubFetchOk();
    const { exchangeLoginTicket } = await import("@/api/auth");

    await exchangeLoginTicket("ticket-1");

    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ loginTicket: "ticket-1" });
  });

  it("reads the session as a GET", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    const fetchMock = stubFetchOk();
    const { getAuthSession } = await import("@/api/auth");

    await getAuthSession();

    expect(fetchMock.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it("rejects a malformed auth response instead of returning it", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(authEnvelope({ authenticated: true })), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const { getAuthSession } = await import("@/api/auth");

    await expect(getAuthSession()).rejects.toThrow();
  });
});
