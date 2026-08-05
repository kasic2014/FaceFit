import { useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import type { InterviewSession } from "@/api/setup";
import { useAuth } from "@/auth/auth-context";
import EquipmentPage from "@/pages/EquipmentPage";

export default function EquipmentApiPage() {
  const { sessionId } = useParams();
  const { request } = useAuth();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void request<InterviewSession>(`/api/v1/interview-sessions/${sessionId}`, { signal: controller.signal })
        .then(() => { if (active) setStatus("ready"); })
        .catch((reason: unknown) => {
          if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
          setMessage(reason instanceof Error ? reason.message : "Unable to load the interview session.");
          setStatus("error");
        });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request, sessionId]);

  if (!sessionId) return <Navigate to="/onboarding" replace />;
  if (status === "loading") return <main className="grid min-h-screen place-items-center bg-ivory-50 text-sm text-ink-700">Loading interview session...</main>;
  if (status === "error") return <main className="grid min-h-screen place-items-center bg-ivory-50 p-5 text-center text-sm text-sunset-700">{message}</main>;
  return <EquipmentPage />;
}
