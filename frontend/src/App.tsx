import { Route, Routes } from "react-router-dom";
import { PrototypeFeedback } from "@/components/facefit/PrototypeFeedback";
import { RequireAuth } from "@/auth/RequireAuth";
import AnalysisPage from "@/pages/AnalysisPage";
import AnalysisApiPage from "@/pages/AnalysisApiPage";
import AccountOnboardingPage from "@/pages/AccountOnboardingPage";
import AccountDataPage from "@/pages/AccountDataPage";
import AuthCallbackPage from "@/pages/AuthCallbackPage";
import DashboardApiPage from "@/pages/DashboardApiPage";
import ConsentPage from "@/pages/ConsentPage";
import EquipmentPage from "@/pages/EquipmentPage";
import EquipmentApiPage from "@/pages/EquipmentApiPage";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";
import OnboardingPage from "@/pages/OnboardingPage";
import PricingPage from "@/pages/PricingPage";
import PolicyPage from "@/pages/PolicyPage";
import RecordApiPage from "@/pages/RecordApiPage";
import ReportPage from "@/pages/ReportPage";
import ReportApiPage from "@/pages/ReportApiPage";
import SessionLivePage from "@/pages/SessionLivePage";
import SessionLiveApiPage from "@/pages/SessionLiveApiPage";
import SessionSettingsApiPage from "@/pages/SessionSettingsApiPage";
import SignupPage from "@/pages/SignupPage";
import SourceResourcesApiPage from "@/pages/SourceResourcesApiPage";
import VoiceProfilePage from "@/pages/VoiceProfilePage";
import VoiceProfileApiPage from "@/pages/VoiceProfileApiPage";

export function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route element={<RequireAuth />}>
          <Route
            path="/account-onboarding"
            element={<AccountOnboardingPage />}
          />
          <Route path="/account/data" element={<AccountDataPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route
            path="/source-resources"
            element={<SourceResourcesApiPage />}
          />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/equipment/:sessionId" element={<EquipmentApiPage />} />
          <Route path="/consent" element={<ConsentPage />} />
          <Route path="/consent/:sessionId" element={<ConsentPage />} />
          <Route path="/voice-profile" element={<VoiceProfilePage />} />
          <Route
            path="/voice-profile/:sessionId"
            element={<VoiceProfileApiPage />}
          />
          <Route path="/session/live" element={<SessionLivePage />} />
          <Route
            path="/sessions/:sessionId/live"
            element={<SessionLiveApiPage />}
          />
          <Route
            path="/sessions/:sessionId/settings"
            element={<SessionSettingsApiPage />}
          />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route
            path="/sessions/:sessionId/analysis"
            element={<AnalysisApiPage />}
          />
          <Route path="/report" element={<ReportPage />} />
          <Route
            path="/sessions/:sessionId/report"
            element={<ReportApiPage />}
          />
          <Route path="/dashboard" element={<DashboardApiPage />} />
          <Route path="/records/:sessionId" element={<RecordApiPage />} />
        </Route>
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/policy" element={<PolicyPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <PrototypeFeedback />
    </>
  );
}
