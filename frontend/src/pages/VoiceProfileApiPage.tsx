import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { type LegalConsentRecord } from "@/api/privacy";
import { createVoiceProfileFormData, type VoiceProfile } from "@/api/voice";
import { parseLegalDocumentList, type LegalDocumentSummary } from "@/api/legal";
import { poll } from "@/api/polling";
import { ApiError } from "@/api/http";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

export default function VoiceProfileApiPage() {
  const { sessionId } = useParams();
  const { request, upload } = useAuth();
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "creating" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void request<VoiceProfile>("/api/v1/voice-profiles/me", { signal: controller.signal })
        .then((value) => { if (active) { setProfile(value); setStatus("ready"); } })
        .catch((reason: unknown) => {
          if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
          if (reason instanceof ApiError && reason.status === 404) { setStatus("ready"); return; }
          setMessage(reason instanceof Error ? reason.message : "Unable to load voice profile status.");
          setStatus("error");
        });
    }, 0);
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [request]);

  const createProfile = async () => {
    if (!file || status === "creating") return;
    setStatus("creating");
    setMessage("");
    try {
      const documents = parseLegalDocumentList(await request<unknown>("/api/v1/legal-documents?type=VOICE_CLONING"));
      const document = documents.find((item: LegalDocumentSummary) => item.type === "VOICE_CLONING");
      if (!document) throw new Error("Voice-cloning consent document is unavailable.");
      const consent = await request<LegalConsentRecord>("/api/v1/legal-consents", { method: "POST", body: { documentId: document.documentId, actionType: document.requiredAction } });
      const initial = await upload<VoiceProfile>("/api/v1/voice-profiles", { method: "POST", formData: createVoiceProfileFormData(consent.consentRecordId, file) });
      setProfile(initial);
      const completed = await poll<VoiceProfile>({
        load: () => request<VoiceProfile>("/api/v1/voice-profiles/me"),
        onValue: setProfile,
        shouldContinue: (value) => value.voiceStatus === "QUEUED" || value.voiceStatus === "PROCESSING" || value.voiceStatus === "DELETING",
        intervalMs: 3000,
        maxWaitMs: 5 * 60 * 1000,
      });
      setProfile(completed);
      setStatus("ready");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to create voice profile.");
      setStatus("error");
    }
  };

  const deleteProfile = async () => {
    if (!profile) return;
    setStatus("creating");
    try {
      const deleting = await request<VoiceProfile>("/api/v1/voice-profiles/me", { method: "DELETE" });
      setProfile(deleting);
      const completed = await poll<VoiceProfile>({ load: () => request<VoiceProfile>("/api/v1/voice-profiles/me"), onValue: setProfile, shouldContinue: (value) => value.voiceStatus === "DELETING", intervalMs: 3000, maxWaitMs: 5 * 60 * 1000 });
      setProfile(completed.voiceStatus === "DELETING" ? completed : null);
      setStatus("ready");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 404) { setProfile(null); setStatus("ready"); return; }
      setMessage(reason instanceof Error ? reason.message : "Unable to delete voice profile.");
      setStatus("error");
    }
  };

  if (!sessionId) return <Navigate to="/onboarding" replace />;
  return <main className="min-h-screen bg-ivory-50 text-ink-900"><PageContainer size="narrow" className="py-14"><Link to={`/equipment/${sessionId}`} className="text-sm font-bold text-moss-800">Back to equipment</Link><section className="mt-6 rounded-2xl border border-line-200 bg-white p-7"><p className="text-sm font-bold text-moss-700">Optional voice profile</p><h1 className="mt-3 text-2xl font-bold">Create a personal improved-answer voice</h1><p className="mt-3 text-sm leading-6 text-ink-600">A separate voice-cloning consent is recorded before upload. Upload an audio sample from 15 to 60 seconds; WebM, MP4, WAV, up to 20MB.</p>{profile ? <div className="mt-6 rounded-xl bg-ivory-100 p-4"><p className="font-bold">Status: {profile.voiceStatus}</p><p className="mt-2 text-sm text-ink-600">{profile.usable ? "Personal audio is available in supported reports." : profile.failureCode ?? "Processing voice profile."}</p><button type="button" onClick={() => void deleteProfile()} disabled={status === "creating"} className="mt-4 rounded-lg border border-sunset-300 px-4 py-2 text-sm font-bold text-sunset-700">Delete voice profile</button></div> : <><input type="file" accept="audio/webm,audio/mp4,audio/wav" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="mt-6 block w-full text-sm" /><button type="button" disabled={!file || status === "creating"} onClick={() => void createProfile()} className="mt-5 rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300">{status === "creating" ? "Creating voice profile" : "Upload sample and create"}</button></>}{message ? <p role="alert" className="mt-5 text-sm text-sunset-700">{message}</p> : null}</section><Link to={`/consent/${sessionId}`} className="mt-6 inline-flex rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700">Skip for now</Link></PageContainer></main>;
}
