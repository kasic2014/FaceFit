import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Upload } from "lucide-react";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { useAuth } from "@/auth/auth-context";
import { poll } from "@/api/polling";
import { createCareerDocumentFormData, createJobPostingFormData, type AiJobRole, type CareerDocument, type Difficulty, type InterviewSession, type JobPosting, type Persona } from "@/api/setup";

const roleOptions: Array<{ value: AiJobRole; label: string }> = [
  { value: "AI_ENGINEER", label: "AI 엔지니어" }, { value: "ML_ENGINEER", label: "ML 엔지니어" }, { value: "DATA_SCIENTIST", label: "데이터 사이언티스트" }, { value: "DATA_ENGINEER", label: "데이터 엔지니어" }, { value: "MLOPS_ENGINEER", label: "MLOps 엔지니어" }, { value: "LLM_ENGINEER", label: "LLM 엔지니어" }, { value: "NLP_ENGINEER", label: "NLP 엔지니어" }, { value: "COMPUTER_VISION_ENGINEER", label: "컴퓨터 비전 엔지니어" }, { value: "AI_PRODUCT_MANAGER", label: "AI 프로덕트 매니저" },
];

function UploadField({ accept, file, label, help, onChange }: { accept: string; file: File | null; label: string; help: string; onChange: (file: File | null) => void }) {
  return <label className="block rounded-2xl border border-line-200 bg-white p-5"><span className="text-sm font-bold text-ink-900">{label}</span><span className="mt-1 block text-xs leading-5 text-ink-500">{help}</span><input type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] ?? null)} className="sr-only" /><span className="mt-4 flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-line-300 bg-ivory-100 px-4 text-center"><Upload size={18} className="text-moss-700" /><span className="mt-2 text-sm font-semibold text-moss-900">파일 선택</span>{file ? <span className="mt-2 flex items-center gap-1 text-xs text-ink-600"><FileText size={13} />{file.name} · {Math.ceil(file.size / 1024)}KB</span> : null}</span></label>;
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { request, upload } = useAuth();
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jobFile, setJobFile] = useState<File | null>(null);
  const [role, setRole] = useState<AiJobRole>("AI_ENGINEER");
  const [persona, setPersona] = useState<Persona>("TECHNICAL");
  const [difficulty, setDifficulty] = useState<Difficulty>("GENERAL");
  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "creating" | "error">("idle");
  const [message, setMessage] = useState("");

  const start = async () => {
    if (!resumeFile || !jobFile || status !== "idle" && status !== "error") return;
    setStatus("uploading");
    setMessage("");
    try {
      const [resume, job] = await Promise.all([
        upload<CareerDocument>("/api/v1/career-documents", { method: "POST", formData: createCareerDocumentFormData(resumeFile) }),
        upload<JobPosting>("/api/v1/job-postings", { method: "POST", formData: createJobPostingFormData(jobFile, role) }),
      ]);
      setStatus("processing");
      const [readyResume, readyJob] = await Promise.all([
        poll({ load: () => request<CareerDocument>(`/api/v1/career-documents/${resume.documentId}`), shouldContinue: (value) => value.status === "PROCESSING", intervalMs: 2000, maxWaitMs: 120000 }),
        poll({ load: () => request<JobPosting>(`/api/v1/job-postings/${job.jobPostingId}`), shouldContinue: (value) => value.processingStatus === "PROCESSING", intervalMs: 2000, maxWaitMs: 120000 }),
      ]);
      if (readyResume.status !== "READY" || readyJob.processingStatus !== "READY") throw new Error("문서 처리에 실패했습니다. 새 파일로 다시 시도해 주세요.");
      setStatus("creating");
      const session = await request<InterviewSession>("/api/v1/interview-sessions", { method: "POST", body: { resumeDocumentId: readyResume.documentId, coverLetterDocumentId: null, jobPostingId: readyJob.jobPostingId, persona, difficulty } });
      navigate(`/equipment/${session.sessionId}`);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "설정을 저장하지 못했습니다. 다시 시도해 주세요.");
    }
  };

  const busy = status === "uploading" || status === "processing" || status === "creating";
  return <div className="flex min-h-screen flex-col bg-ivory-50"><AppNav active="새 면접" /><PageContainer as="main" size="standard" className="flex-1 py-10"><header className="mb-8"><h1 className="text-3xl font-bold tracking-[-.04em] text-ink-900">새 면접 설정</h1><p className="mt-2 text-sm text-ink-600">이력서와 지원공고 파일을 바탕으로 면접 질문을 준비합니다.</p></header><div className="grid gap-5 lg:grid-cols-2"><UploadField label="이력서" help="PDF 또는 DOCX · 최대 10MB" accept="application/pdf,.docx" file={resumeFile} onChange={setResumeFile} /><UploadField label="지원공고" help="PDF 또는 JPG/JPEG/PNG · 최대 10MB" accept="application/pdf,image/jpeg,image/png" file={jobFile} onChange={setJobFile} /></div><section className="mt-5 grid gap-5 rounded-2xl border border-line-200 bg-white p-6 md:grid-cols-3"><label className="text-sm font-bold text-ink-900">지원 직무<select value={role} onChange={(event) => setRole(event.target.value as AiJobRole)} disabled={busy} className="mt-2 w-full rounded-xl border border-line-300 bg-white p-3 text-sm font-medium"><option value="">직무 선택</option>{roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label className="text-sm font-bold text-ink-900">면접관<select value={persona} onChange={(event) => setPersona(event.target.value as Persona)} disabled={busy} className="mt-2 w-full rounded-xl border border-line-300 bg-white p-3 text-sm font-medium"><option value="TECHNICAL">기술 면접관</option><option value="HR">HR 면접관</option><option value="EXECUTIVE">경영진 면접관</option></select></label><label className="text-sm font-bold text-ink-900">면접 강도<select value={difficulty} onChange={(event) => setDifficulty(event.target.value as Difficulty)} disabled={busy} className="mt-2 w-full rounded-xl border border-line-300 bg-white p-3 text-sm font-medium"><option value="GENERAL">일반</option><option value="PRESSURE">압박</option></select></label></section>{message ? <p role="alert" className="mt-5 rounded-xl border border-sunset-200 bg-white p-4 text-sm text-sunset-700">{message}</p> : null}<div className="mt-8 flex justify-end border-t border-line-200 pt-6"><button type="button" onClick={() => void start()} disabled={!resumeFile || !jobFile || busy} className="min-h-12 rounded-xl bg-sunset-600 px-7 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300">{status === "uploading" ? "파일 업로드 중" : status === "processing" ? "문서 처리 중" : status === "creating" ? "세션 생성 중" : "면접 시작하기"}</button></div></PageContainer></div>;
}
