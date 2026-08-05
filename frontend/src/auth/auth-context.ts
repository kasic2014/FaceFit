import { createContext, useContext } from "react";
import type { AuthData } from "@/api/auth";
import type { ApiResponse, BinaryRequestOptions, JsonRequestOptions, MultipartRequestOptions } from "@/api/http";

export type AuthStatus = "unconfigured" | "loading" | "authenticated" | "anonymous" | "error";

export type AuthContextValue = {
  auth: AuthData | null;
  status: AuthStatus;
  backendConfigured: boolean;
  completeLogin: (auth: AuthData) => void;
  refresh: () => Promise<AuthData | null>;
  retryBootstrap: () => Promise<void>;
  signOut: () => Promise<void>;
  request: <T>(path: string, options?: JsonRequestOptions) => Promise<T>;
  requestWithResponse: <T>(path: string, options?: JsonRequestOptions) => Promise<ApiResponse<T>>;
  upload: <T>(path: string, options: MultipartRequestOptions) => Promise<T>;
  binary: (path: string, options?: Omit<BinaryRequestOptions, "accessToken">) => Promise<Response>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
