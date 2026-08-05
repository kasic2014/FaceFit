import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { PrototypeFeedback } from "@/components/facefit/PrototypeFeedback";
import { RequireAuth } from "@/auth/RequireAuth";
import { RequireOnboardingComplete, RequireOnboardingIncomplete } from "@/auth/RequireOnboarding";

const AccountDataPage = lazy(() => import("@/pages/AccountDataPage"));
const AccountOnboardingPage = lazy(() => import("@/pages/AccountOnboardingPage"));
const AnalysisApiPage = lazy(() => import("@/pages/AnalysisApiPage"));
const AuthCallbackPage = lazy(() => import("@/pages/AuthCallbackPage"));
const ConsentPage = lazy(() => import("@/pages/ConsentPage"));
const DashboardApiPage = lazy(() => import("@/pages/DashboardApiPage"));
const EquipmentApiPage = lazy(() => import("@/pages/EquipmentApiPage"));
const HomePage = lazy(() => import("@/pages/HomePage"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));
const OnboardingPage = lazy(() => import("@/pages/OnboardingPage"));
const PolicyPage = lazy(() => import("@/pages/PolicyPage"));
const PricingPage = lazy(() => import("@/pages/PricingPage"));
const RecordApiPage = lazy(() => import("@/pages/RecordApiPage"));
const ReportApiPage = lazy(() => import("@/pages/ReportApiPage"));
const SessionLiveApiPage = lazy(() => import("@/pages/SessionLiveApiPage"));
const SessionSettingsApiPage = lazy(() => import("@/pages/SessionSettingsApiPage"));
const SignupPage = lazy(() => import("@/pages/SignupPage"));
const SourceResourcesApiPage = lazy(() => import("@/pages/SourceResourcesApiPage"));
const VoiceProfileApiPage = lazy(() => import("@/pages/VoiceProfileApiPage"));

function RouteFallback() {
  return (
    <main
      aria-busy="true"
      className="grid min-h-screen place-items-center bg-ivory-50 text-sm text-ink-500"
    >
      화면을 불러오는 중입니다.
    </main>
  );
}

export function App() {
  return (
    <>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<RequireOnboardingIncomplete />}>
            <Route
              path="/account-onboarding"
              element={<AccountOnboardingPage />}
            />
          </Route>
          <Route element={<RequireOnboardingComplete />}>
            <Route path="/account/data" element={<AccountDataPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route
              path="/source-resources"
              element={<SourceResourcesApiPage />}
            />
            <Route path="/equipment/:sessionId" element={<EquipmentApiPage />} />
            <Route path="/consent/:sessionId" element={<ConsentPage />} />
            <Route
              path="/voice-profile/:sessionId"
              element={<VoiceProfileApiPage />}
            />
            <Route
              path="/sessions/:sessionId/live"
              element={<SessionLiveApiPage />}
            />
            <Route
              path="/sessions/:sessionId/settings"
              element={<SessionSettingsApiPage />}
            />
            <Route
              path="/sessions/:sessionId/analysis"
              element={<AnalysisApiPage />}
            />
            <Route
              path="/sessions/:sessionId/report"
              element={<ReportApiPage />}
            />
            <Route path="/dashboard" element={<DashboardApiPage />} />
            <Route path="/records/:sessionId" element={<RecordApiPage />} />
          </Route>
        </Route>
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/policy" element={<PolicyPage />} />
        <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
      <PrototypeFeedback />
    </>
  );
}
