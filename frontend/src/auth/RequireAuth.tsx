import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/auth-context";

export function RequireAuth() {
  const { backendConfigured, status } = useAuth();

  if (!backendConfigured) return <Outlet />;
  if (status === "loading") return <main className="grid min-h-screen place-items-center bg-ivory-50 text-sm text-ink-600">세션을 확인하고 있어요.</main>;
  if (status === "authenticated") return <Outlet />;

  return <Navigate to="/login" replace />;
}
