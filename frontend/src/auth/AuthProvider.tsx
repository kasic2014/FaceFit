import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { type AuthData, getAuthSession, logout, refreshAuthSession } from "@/api/auth";
import { isApiConfigured } from "@/api/config";
import { ApiError, requestBinary, requestJson, requestJsonWithResponse, requestMultipart, type BinaryRequestOptions, type JsonRequestOptions, type MultipartRequestOptions } from "@/api/http";
import { AuthContext, type AuthContextValue, type AuthStatus } from "@/auth/auth-context";

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

  const request = useCallback(async <T,>(path: string, options: JsonRequestOptions = {}) => {
    const method = options.method?.toUpperCase() ?? "GET";
    const canRetryAfterRefresh = method === "GET" || method === "HEAD";

    try {
      return await requestJson<T>(path, {
        ...options,
        accessToken: authRef.current?.accessToken ?? null,
      });
    } catch (error) {
      if (!canRetryAfterRefresh || !(error instanceof ApiError) || error.status !== 401) throw error;

      const refreshed = await refresh();
      if (!refreshed?.accessToken) throw error;

      return requestJson<T>(path, {
        ...options,
        accessToken: refreshed.accessToken,
      });
    }
  }, [refresh]);

  const requestWithResponse = useCallback(<T,>(path: string, options: JsonRequestOptions = {}) => requestJsonWithResponse<T>(path, {
    ...options,
    accessToken: authRef.current?.accessToken ?? null,
  }), []);

  const upload = useCallback(<T,>(path: string, options: MultipartRequestOptions) => requestMultipart<T>(path, {
    ...options,
    accessToken: authRef.current?.accessToken ?? null,
  }), []);

  const binary = useCallback(async (path: string, options: Omit<BinaryRequestOptions, "accessToken"> = {}) => {
    try {
      return await requestBinary(path, { ...options, accessToken: authRef.current?.accessToken ?? null });
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      const refreshed = await refresh();
      if (!refreshed?.accessToken) throw error;
      return requestBinary(path, { ...options, accessToken: refreshed.accessToken });
    }
  }, [refresh]);

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
