import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { useAuth } from "@/auth/auth-context";
import { type AccountOnboardingResult, type LegalDocumentDetail, parseLegalDocumentDetail, parseLegalDocumentList } from "@/api/legal";

export default function AccountOnboardingPage() {
  const navigate = useNavigate();
  const { auth, request, refresh } = useAuth();
  const [documents, setDocuments] = useState<LegalDocumentDetail[]>([]);
  const [actions, setActions] = useState<Record<string, boolean>>({});
  const [voiceAnalysisConsent, setVoiceAnalysisConsent] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "submitting" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;

    void request<unknown>("/api/v1/legal-documents")
      .then(parseLegalDocumentList)
      .then(async (summaries) => Promise.all(summaries
        .filter((document) => document.requiredForOnboarding)
        .map(async (document) => parseLegalDocumentDetail(await request<unknown>(`/api/v1/legal-documents/${document.documentId}`)))))
      .then((details) => {
        if (!active) return;
        setDocuments(details);
        setStatus("ready");
      })
      .catch(() => {
        if (!active) return;
        setMessage("필수 약관을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
        setStatus("error");
      });

    return () => {
      active = false;
    };
  }, [request]);

  const allRequiredActionsDone = useMemo(
    () => documents.every((document) => actions[document.documentId] === true),
    [actions, documents],
  );

  const submit = async () => {
    if (!allRequiredActionsDone || status === "submitting") return;
    setStatus("submitting");
    setMessage("");

    try {
      await request<AccountOnboardingResult>("/api/v1/members/me/onboarding", {
        method: "PATCH",
        body: {
          voiceAnalysisConsent,
          legalActions: documents.map((document) => ({
            documentId: document.documentId,
            actionType: document.requiredAction,
          })),
        },
      });
      await refresh();
      navigate("/onboarding", { replace: true });
    } catch {
      setMessage("동의 내용을 저장하지 못했습니다. 선택을 유지한 채 다시 시도할 수 있어요.");
      setStatus("ready");
    }
  };

  return <main className="min-h-screen bg-ivory-50"><PageContainer size="compact" className="py-12 md:py-16"><p className="text-sm font-bold text-sunset-700">FACE FIT ACCOUNT</p><h1 className="mt-3 text-3xl font-bold tracking-[-.04em] text-ink-900">환영합니다{auth?.member ? `, ${auth.member.name}님` : ""}.</h1><p className="mt-4 text-sm leading-7 text-ink-600">서비스 이용에 필요한 약관을 확인하고 동의해 주세요.</p>{status === "loading" && <p role="status" className="mt-8 text-sm text-ink-600">약관을 불러오고 있어요.</p>}{status === "error" && <div className="mt-8 rounded-xl border border-sunset-200 bg-white p-5"><p className="text-sm leading-6 text-ink-700">{message}</p><Link to="/login" className="mt-4 inline-flex text-sm font-bold text-moss-700 underline underline-offset-4">로그인 화면으로</Link></div>}{(status === "ready" || status === "submitting") && <section className="mt-8 space-y-4">{documents.map((document) => <article key={document.documentId} className="rounded-2xl border border-line-300 bg-white p-5"><p className="text-sm font-bold text-ink-900">{document.title}</p><p className="mt-1 text-xs text-ink-500">버전 {document.version} · 시행일 {document.effectiveAt}</p><p className="mt-4 max-h-40 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-ink-700">{document.content}</p><label className="mt-5 flex cursor-pointer items-start gap-3 text-sm font-semibold text-ink-900"><input type="checkbox" checked={actions[document.documentId] === true} onChange={(event) => setActions((current) => ({ ...current, [document.documentId]: event.target.checked }))} disabled={status === "submitting"} className="mt-0.5 size-4 accent-moss-900" />{document.requiredAction === "CONSENTED" ? "내용에 동의합니다." : "내용을 확인했습니다."}</label></article>)}<label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-line-300 bg-white p-5 text-sm text-ink-700"><input type="checkbox" checked={voiceAnalysisConsent} onChange={(event) => setVoiceAnalysisConsent(event.target.checked)} disabled={status === "submitting"} className="mt-0.5 size-4 accent-moss-900" /><span><strong className="block text-ink-900">음성 분석 동의 (선택)</strong><span className="mt-1 block leading-6">발화 속도와 휴지 분석에 사용합니다. 음성 복제 동의와는 별도입니다.</span></span></label>{message && <p role="alert" className="rounded-xl border border-sunset-200 bg-white p-4 text-sm leading-6 text-sunset-700">{message}</p>}<button type="button" onClick={() => void submit()} disabled={!allRequiredActionsDone || status === "submitting"} className="inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-moss-900 px-5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300 disabled:text-ink-500">{status === "submitting" ? "동의를 저장하고 있어요" : "동의하고 시작하기"}</button></section>}</PageContainer></main>;
}
