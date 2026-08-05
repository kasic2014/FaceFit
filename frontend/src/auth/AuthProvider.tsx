import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { type AuthData, getAuthSession, logout, refreshAuthSession } from "@/api/auth";
import { isApiConfigured } from "@/api/config";
import { requestBinary, requestJson, requestJsonWithResponse, requestMultipart, type BinaryRequestOptions, type JsonRequestOptions, type MultipartRequestOptions } from "@/api/http";
import { AuthContext, type AuthContextValue, type AuthStatus } from "@/auth/auth-context";
import { withAuthRetry } from "@/auth/with-auth-retry";

function getStatus(auth: AuthData): AuthStatus {
  return auth.authenticated && auth.accessToken ? "authenticated" : "anonymous";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const backendConfigured = isApiConfigured();
  const [auth, setAuth] = useState<AuthData | null>(null);
  const [status, setStatus] = useState<AuthStatus>(backendConfigured ? "loading" : "unconfigured");
  const authRef = useRef<AuthData | null>(null);
  const refreshPromise = useRef<Promise<AuthData | null> | null>(null);

  const setAuthState = useCallback((nextAuth: AuthData | null, nextStatus?: AuthStatus) => {
    authRef.current = nextAuth;
    setAuth(nextAuth);
    setStatus(nextStatus ?? (nextAuth ? getStatus(nextAuth) : "anonymous"));
  }, []);

  const retryBootstrap = useCallback(async () => {
    if (!backendConfigured) return;
    setStatus("loading");

    try {
      setAuthState(await getAuthSession());
    } catch {
      setAuthState(null, "error");
    }
  }, [backendConfigured, setAuthState]);

  useEffect(() => {
    const bootstrapTimer = window.setTimeout(() => {
      void retryBootstrap();
    }, 0);

    return () => window.clearTimeout(bootstrapTimer);
  }, [retryBootstrap]);

  const refresh = useCallback(async () => {
    if (!backendConfigured) return null;
    if (refreshPromise.current) return refreshPromise.current;

    refreshPromise.current = refreshAuthSession()
      .then((nextAuth) => {
        setAuthState(nextAuth);
        return nextAuth.authenticated && nextAuth.accessToken ? nextAuth : null;
      })
      .catch(() => {
        setAuthState(null, "anonymous");
        return null;
      })
      .finally(() => {
        refreshPromise.current = null;
      });

    return refreshPromise.current;
  }, [backendConfigured, setAuthState]);

  const signOut = useCallback(async () => {
    if (backendConfigured) {
      try {
        await logout();
      } finally {
        setAuthState(null, "anonymous");
      }
      return;
    }

    setAuthState(null, "unconfigured");
  }, [backendConfigured, setAuthState]);

  const getAccessToken = useCallback(() => authRef.current?.accessToken ?? null, []);

  const request = useCallback(<T,>(path: string, options: JsonRequestOptions = {}) => {
    const method = options.method?.toUpperCase() ?? "GET";
    const canRetry = method === "GET" || method === "HEAD";
    return withAuthRetry<T>(canRetry, (accessToken) => requestJson<T>(path, { ...options, accessToken }), getAccessToken, refresh);
  }, [getAccessToken, refresh]);

  const requestWithResponse = useCallback(<T,>(path: string, options: JsonRequestOptions = {}) => {
    const method = options.method?.toUpperCase() ?? "GET";
    const canRetry = method === "GET" || method === "HEAD";
    return withAuthRetry(canRetry, (accessToken) => requestJsonWithResponse<T>(path, { ...options, accessToken }), getAccessToken, refresh);
  }, [getAccessToken, refresh]);

  // ponytail: uploads always retry after refresh — ANSWER-001 carries an Idempotency-Key, so a retried upload is safe.
  const upload = useCallback(<T,>(path: string, options: MultipartRequestOptions) =>
    withAuthRetry<T>(true, (accessToken) => requestMultipart<T>(path, { ...options, accessToken }), getAccessToken, refresh),
  [getAccessToken, refresh]);

  const binary = useCallback((path: string, options: Omit<BinaryRequestOptions, "accessToken"> = {}) =>
    withAuthRetry(true, (accessToken) => requestBinary(path, { ...options, accessToken }), getAccessToken, refresh),
  [getAccessToken, refresh]);

  const value = useMemo<AuthContextValue>(() => ({
    auth,
    status,
    backendConfigured,
    completeLogin: setAuthState,
    refresh,
    retryBootstrap,
    signOut,
    request,
    requestWithResponse,
    upload,
    binary,
  }), [auth, backendConfigured, binary, refresh, request, requestWithResponse, retryBootstrap, setAuthState, signOut, status, upload]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
