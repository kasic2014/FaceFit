import { requestJson, type JsonRequestOptions } from "@/api/http";
import type { components } from "@/api/generated/facefit";

export type NextAction = components["schemas"]["NextAction"];
export type MemberSummary = components["schemas"]["MemberSummary"];
export type AuthData = components["schemas"]["AuthData"];

function isAuthData(value: unknown): value is AuthData {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const data = value as Record<string, unknown>;
  return typeof data.authenticated === "boolean"
    && (typeof data.accessToken === "string" || data.accessToken === null)
    && (typeof data.accessTokenExpiresInSec === "number" || data.accessTokenExpiresInSec === null)
    && (typeof data.nextAction === "string");
}

async function readAuthData(path: string, init: JsonRequestOptions = {}) {
  const data = await requestJson<unknown>(path, init);
  if (!isAuthData(data)) throw new Error("Auth API returned an invalid response shape.");
  return data;
}

export function getAuthSession() {
  return readAuthData("/api/v1/auth/session");
}

export function refreshAuthSession() {
  return readAuthData("/api/v1/auth/token/refresh", { method: "POST" });
}

export function exchangeLoginTicket(loginTicket: string) {
  return readAuthData("/api/v1/auth/oauth/exchange", { method: "POST", body: { loginTicket } });
}

export function logout() {
  return requestJson<void>("/api/v1/auth/logout", { method: "POST" });
}
