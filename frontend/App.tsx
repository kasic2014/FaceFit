import { Route, Routes } from "react-router-dom";
import { PrototypeFeedback } from "@/components/facefit/PrototypeFeedback";
import AnalysisPage from "@/pages/AnalysisPage";
import DashboardPage from "@/pages/DashboardPage";
import DesignPreviewPage from "@/pages/DesignPreviewPage";
import EquipmentPage from "@/pages/EquipmentPage";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";
import OnboardingPage from "@/pages/OnboardingPage";
import PricingPage from "@/pages/PricingPage";
import ReportPage from "@/pages/ReportPage";
import SessionLivePage from "@/pages/SessionLivePage";
import SignupPage from "@/pages/SignupPage";
import VoiceProfilePage from "@/pages/VoiceProfilePage";

export function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/equipment" element={<EquipmentPage />} />
        <Route path="/voice-profile" element={<VoiceProfilePage />} />
        <Route path="/session/live" element={<SessionLivePage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/design-preview" element={<DesignPreviewPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <PrototypeFeedback />
    </>
  );
}
