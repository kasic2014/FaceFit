import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router";
import { type LegalConsentRecord } from "@/api/privacy";
import { createVoiceProfileFormData, type VoiceProfile } from "@/api/voice";
import { parseLegalDocumentList, type LegalDocumentSummary } from "@/api/legal";
import { poll } from "@/api/polling";
import { ApiError } from "@/api/http";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { useVoiceSampleRecorder } from "@/hooks/useVoiceSampleRecorder";

const guideScript =
  "안녕하세요. 저는 맡은 일을 끝까지 책임지고 해결하는 지원자입니다. 프로젝트를 진행할 때는 먼저 문제의 원인을 분석하고, 팀원들과 해결 방법을 공유한 뒤 우선순위에 따라 작업합니다. 앞으로도 꾸준히 배우면서 팀에 도움이 되는 개발자로 성장하겠습니다.";

function formatSeconds(ms: number) {
  return `${Math.floor(ms / 1000)}초`;
}

export default function VoiceProfileApiPage() {
  const { sessionId } = useParams();
  const { request, upload } = useAuth();
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "creating" | "error">("loading");
  const [message, setMessage] = useState("");
  const recorder = useVoiceSampleRecorder();
  const sample = recorder.file ?? file;

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
    if (!sample || status === "creating") return;
    setStatus("creating");
    setMessage("");
    try {
      const documents = parseLegalDocumentList(await request<unknown>("/api/v1/legal-documents?type=VOICE_CLONING"));
      const document = documents.find((item: LegalDocumentSummary) => item.type === "VOICE_CLONING");
      if (!document) throw new Error("Voice-cloning consent document is unavailable.");
      const consent = await request<LegalConsentRecord>("/api/v1/legal-consents", { method: "POST", body: { documentId: document.documentId, actionType: document.requiredAction } });
      const initial = await upload<VoiceProfile>("/api/v1/voice-profiles", { method: "POST", formData: createVoiceProfileFormData(consent.consentRecordId, sample) });
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
  return <main className="min-h-screen bg-ivory-50 text-ink-900"><PageContainer size="narrow" className="py-14"><Link to={`/equipment/${sessionId}`} className="text-sm font-bold text-moss-800">Back to equipment</Link><section className="mt-6 rounded-2xl border border-line-200 bg-white p-7"><p className="text-sm font-bold text-moss-700">Optional voice profile</p><h1 className="mt-3 text-2xl font-bold">Create a personal improved-answer voice</h1><p className="mt-3 text-sm leading-6 text-ink-600">A separate voice-cloning consent is recorded before upload. Upload an audio sample from 15 to 60 seconds; WebM, MP4, WAV, up to 20MB.</p>{profile ? <div className="mt-6 rounded-xl bg-ivory-100 p-4"><p className="font-bold">Status: {profile.voiceStatus}</p><p className="mt-2 text-sm text-ink-600">{profile.usable ? "Personal audio is available in supported reports." : profile.failureCode ?? "Processing voice profile."}</p><button type="button" onClick={() => void deleteProfile()} disabled={status === "creating"} className="mt-4 rounded-lg border border-sunset-300 px-4 py-2 text-sm font-bold text-sunset-700">Delete voice profile</button></div> : <>
      <div className="mt-6 rounded-xl bg-ivory-100 p-4">
        <p className="text-sm font-bold text-ink-800">아래 문장을 소리 내어 읽어 주세요</p>
        <p className="mt-2 text-sm leading-6 text-ink-600">{guideScript}</p>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        {recorder.state === "recording" ? (
          <button type="button" onClick={recorder.stop} className="rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold text-white">녹음 정지 ({formatSeconds(recorder.elapsedMs)})</button>
        ) : (
          <button type="button" onClick={() => void recorder.start()} disabled={recorder.state === "requesting" || status === "creating"} className="rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300">{recorder.state === "requesting" ? "마이크 권한 요청 중" : recorder.state === "ready" ? "다시 녹음" : "녹음 시작"}</button>
        )}
        {recorder.state === "ready" ? <span className="text-sm text-ink-600">{formatSeconds(recorder.durationMs)} 녹음됨</span> : null}
      </div>
      {recorder.previewUrl ? <audio src={recorder.previewUrl} controls className="mt-4 w-full" /> : null}
      {recorder.message ? <p role="alert" className="mt-3 text-sm text-sunset-700">{recorder.message}</p> : null}
      <p className="mt-6 text-sm text-ink-600">직접 녹음한 파일이 있다면 업로드해도 됩니다.</p>
      <input type="file" accept="audio/webm,audio/mp4,audio/wav" onChange={(event) => { recorder.reset(); setFile(event.target.files?.[0] ?? null); }} className="mt-2 block w-full text-sm" />
      <button type="button" disabled={!sample || status === "creating"} onClick={() => void createProfile()} className="mt-5 rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300">{status === "creating" ? "Creating voice profile" : "Upload sample and create"}</button>
    </>}{message ? <p role="alert" className="mt-5 text-sm text-sunset-700">{message}</p> : null}</section><Link to={`/consent/${sessionId}`} className="mt-6 inline-flex rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700">Skip for now</Link></PageContainer></main>;
}
