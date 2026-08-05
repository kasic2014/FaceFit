import { useEffect, useState } from "react";
import type { components } from "@/api/generated/facefit";
import { useAuth } from "@/auth/auth-context";

type QuestionContextTransparency = components["schemas"]["QuestionContextTransparency"];

export function QuestionContextPanel({ sessionId }: { sessionId: string }) {
  const { request } = useAuth();
  const [context, setContext] = useState<QuestionContextTransparency | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || context) return;
    const controller = new AbortController();
    void request<QuestionContextTransparency>(`/api/v1/interview-sessions/${sessionId}/question-context`, { signal: controller.signal })
      .then(setContext)
      .catch(() => undefined);
    return () => controller.abort();
  }, [context, open, request, sessionId]);

  return <section className="mt-7 rounded-2xl border border-line-200 bg-white p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold">Question generation context</h2><p className="mt-1 text-sm text-ink-600">View the approved summaries used to prepare questions. Source documents and transcripts are never exposed here.</p></div><button type="button" onClick={() => setOpen((value) => !value)} className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700">{open ? "Hide context" : "View context"}</button></div>{open ? <div className="mt-5 space-y-4">{context ? <>{context.questions.map((question) => <div key={question.questionId} className="rounded-xl bg-ivory-100 p-4"><p className="text-xs font-bold text-ink-500">QUESTION {question.questionId}</p>{question.evidence.map((evidence) => <div key={evidence.evidenceId} className="mt-3"><p className="font-bold text-moss-800">{evidence.title}</p><p className="mt-1 text-sm leading-6 text-ink-600">{evidence.summary}</p></div>)}</div>)}</> : <p role="status" className="text-sm text-ink-600">Loading approved question context...</p>}</div> : null}</section>;
}
