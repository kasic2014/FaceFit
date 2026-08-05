import { Navigate, Outlet } from "react-router";
import { useAuth } from "@/auth/auth-context";

function useOnboardingIncomplete() {
  const { auth } = useAuth();
  return auth?.nextAction === "COMPLETE_ONBOARDING";
}

/** Wraps every authenticated route except /account-onboarding. Sends members who haven't finished onboarding back to it. */
export function RequireOnboardingComplete() {
  const incomplete = useOnboardingIncomplete();
  if (incomplete) return <Navigate to="/account-onboarding" replace />;
  return <Outlet />;
}

/** Wraps /account-onboarding. Sends members who already finished onboarding to the dashboard. */
export function RequireOnboardingIncomplete() {
  const incomplete = useOnboardingIncomplete();
  if (!incomplete) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
