import { useEffect, useState } from "react";
import { Check, ChevronLeft, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { parseLegalDocumentList, type LegalDocumentSummary } from "@/api/legal";
import { createIdempotencyKey } from "@/api/polling";
import { useAuth } from "@/auth/auth-context";

export default function ConsentPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { request } = useAuth();
  const [document, setDocument] = useState<LegalDocumentSummary | null>(null);
  const [checked, setChecked] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "starting" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!sessionId) return;
    void request<unknown>("/api/v1/legal-documents?type=INTERVIEW_MEDIA_PROCESSING")
      .then(parseLegalDocumentList)
      .then((documents) => {
        const activeDocument = documents.find((item) => item.type === "INTERVIEW_MEDIA_PROCESSING");
        if (!activeDocument) throw new Error("면접 미디어 처리 동의 문서를 찾지 못했습니다.");
        setDocument(activeDocument);
        setStatus("ready");
      })
      .catch((error) => {
        setMessage(error instanceof Error ? error.message : "동의 문서를 불러오지 못했습니다.");
        setStatus("error");
      });
  }, [request, sessionId]);

  const start = async () => {
    if (!sessionId || !document || !checked || status === "starting") return;
    setStatus("starting");
    setMessage("");
    try {
      await request("/api/v1/legal-consents", { method: "POST", body: { documentId: document.documentId, actionType: document.requiredAction, context: { sessionId } } });
      await request(`/api/v1/interview-sessions/${sessionId}/start`, { method: "POST", headers: { "Idempotency-Key": createIdempotencyKey() } });
      navigate(`/sessions/${sessionId}/live`, { replace: true });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "동의 또는 면접 시작 요청을 처리하지 못했습니다.");
      setStatus("ready");
    }
  };

  if (!sessionId) return <main className="grid min-h-screen place-items-center bg-ivory-50 p-5 text-center text-sm text-ink-700">유효한 면접 세션이 없습니다. 새 면접 설정부터 다시 시작해 주세요.</main>;

  return <div className="min-h-screen bg-ivory-50 text-ink-900"><AppNav active="AI 면접" /><PageContainer as="main" size="narrow" className="py-10 md:py-14"><Link to={`/equipment/${sessionId}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-moss-900"><ChevronLeft size={16} />장비 확인으로 돌아가기</Link><section className="mt-6 rounded-[22px] border border-line-200 bg-white p-7 shadow-[0_18px_50px_rgba(32,42,35,.06)] md:p-10"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf4ef] text-moss-900"><ShieldCheck size={24} /></span><p className="mt-6 text-sm font-bold text-sunset-700">BEFORE YOU START</p><h1 className="mt-2 text-3xl font-bold tracking-[-.05em]">면접 미디어 처리 동의</h1><p className="mt-4 text-sm leading-7 text-ink-600">카메라·마이크 녹화는 이 면접 세션의 질문 진행과 분석에만 사용됩니다.</p>{status === "loading" ? <p role="status" className="mt-8 text-sm text-ink-600">동의 문서를 불러오고 있어요.</p> : null}{document ? <label className="mt-8 flex cursor-pointer items-start gap-3 rounded-xl border border-line-200 p-4 transition hover:border-moss-300"><input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} disabled={status === "starting"} className="mt-0.5 size-5 accent-[#33583f]" /><span className="text-sm leading-6 text-ink-700"><strong className="block text-ink-900">{document.title}</strong><span className="mt-1 block">버전 {document.version} · {document.requiredAction === "CONSENTED" ? "내용에 동의합니다." : "내용을 확인했습니다."}</span></span></label> : null}{message ? <p role="alert" className="mt-5 rounded-xl border border-sunset-200 bg-white p-4 text-sm text-sunset-700">{message}</p> : null}<div className="mt-6 rounded-xl bg-[#f7f6f1] p-4 text-sm leading-6 text-ink-600"><Check className="mr-2 inline size-4 text-moss-700" />동의 기록은 서버에 세션 ID와 함께 저장됩니다. 원본 미디어는 공개 URL로 제공되지 않습니다.</div><button type="button" disabled={!checked || status !== "ready"} onClick={() => void start()} className="mt-8 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-sunset-600 px-5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300 disabled:text-ink-400">{status === "starting" ? "면접을 준비하고 있어요" : "동의하고 면접 시작하기"}</button></section></PageContainer></div>;
}
