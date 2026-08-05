import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { type AnalysisStatus } from "@/api/analysis";
import { createIdempotencyKey, poll } from "@/api/polling";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

const stageLabels = {
  PREPARING: "Preparing analysis",
  VOICE: "Analyzing speech",
  VISION: "Analyzing video",
  CONTENT: "Analyzing answers",
  REPORT: "Generating report",
} as const;

export default function AnalysisApiPage() {
  const { sessionId } = useParams();
  const { request } = useAuth();
  const [analysis, setAnalysis] = useState<AnalysisStatus | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void poll<AnalysisStatus>({
        load: () => request<AnalysisStatus>(`/api/v1/interview-sessions/${sessionId}/analysis-status`, { signal: controller.signal }),
        onValue: (value) => {
          if (active) setAnalysis(value);
        },
        shouldContinue: (value) => value.analysisStatus === "WAITING" || value.analysisStatus === "PROCESSING" || value.reportStatus === "QUEUED" || value.reportStatus === "PROCESSING",
        retryAfterMs: (value) => value.retryAfterSec === null ? null : value.retryAfterSec * 1000,
        intervalMs: (elapsedMs) => elapsedMs < 30000 ? 3000 : 10000,
        maxWaitMs: 10 * 60 * 1000,
        signal: controller.signal,
      }).catch((reason: unknown) => {
        if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "Unable to load analysis status.");
      });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [reloadKey, request, sessionId]);

  const retry = async () => {
    if (!sessionId || !analysis?.retryable) return;
    setRetrying(true);
    setError("");
    try {
      const next = await request<AnalysisStatus>(`/api/v1/interview-sessions/${sessionId}/analysis-retry`, {
        method: "POST",
        headers: { "Idempotency-Key": createIdempotencyKey() },
        body: { failedStepsOnly: true },
      });
      setAnalysis(next);
      setReloadKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to retry analysis.");
    } finally {
      setRetrying(false);
    }
  };

  if (!sessionId) return <Navigate to="/onboarding" replace />;

  const isFailed = analysis?.analysisStatus === "FAILED" || analysis?.reportStatus === "FAILED";
  const canOpenReport = analysis?.reportStatus === "SUCCEEDED";
  const completedTasks = analysis?.succeededRequiredTaskCount ?? 0;
  const totalTasks = analysis?.totalRequiredTaskCount ?? 0;
  const progressBlocks = Math.round((analysis?.progressPercent ?? 0) / 10);

  return (
    <main className="min-h-screen bg-ivory-50 text-ink-900">
      <PageContainer size="narrow" className="py-14">
        <section className="rounded-2xl border border-line-200 bg-white p-7 shadow-sm">
          <p className="text-sm font-bold text-moss-700">Interview analysis</p>
          <h1 className="mt-3 text-2xl font-bold">
            {isFailed ? "Analysis needs attention" : canOpenReport ? "Your report is ready" : "We are preparing your report"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            {analysis ? `${stageLabels[analysis.currentUiStage]} - ${completedTasks}/${totalTasks} required tasks complete` : "Loading server status..."}
          </p>
          <div className="mt-7 grid grid-cols-10 gap-1" aria-label={`Analysis progress ${analysis?.progressPercent ?? 0}%`}>
            {Array.from({ length: 10 }, (_, index) => <span key={index} className={index < progressBlocks ? "h-2 rounded-full bg-moss-700" : "h-2 rounded-full bg-ivory-200"} />)}
          </div>
          <p className="mt-2 text-right text-sm font-semibold text-moss-800">{analysis?.progressPercent.toFixed(1) ?? "0.0"}%</p>
          {analysis ? <div className="mt-7 grid gap-3 sm:grid-cols-2">
            {Object.entries(analysis.stages).map(([name, stage]) => <div key={name} className="rounded-xl bg-ivory-100 p-4">
              <p className="text-sm font-bold uppercase text-ink-800">{name}</p>
              <p className="mt-2 text-sm text-ink-600">{stage.succeeded}/{stage.total} complete - {stage.failed} failed</p>
            </div>)}
          </div> : null}
          {analysis?.failureCode ? <p role="alert" className="mt-6 rounded-xl border border-sunset-300 bg-sunset-100 p-4 text-sm text-sunset-800">{analysis.failureCode}</p> : null}
          {error ? <p role="alert" className="mt-6 rounded-xl border border-sunset-300 bg-sunset-100 p-4 text-sm text-sunset-800">{error}</p> : null}
          <div className="mt-7 flex flex-wrap gap-3">
            {canOpenReport ? <Link to={`/sessions/${sessionId}/report`} className="rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white">Open report</Link> : null}
            {isFailed && analysis?.retryable ? <button type="button" onClick={() => void retry()} disabled={retrying} className="inline-flex items-center gap-2 rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white"><RefreshCw size={16} className={retrying ? "animate-spin" : ""} />{retrying ? "Retrying" : "Retry failed steps"}</button> : null}
            <Link to="/dashboard" className="rounded-xl border border-line-300 px-5 py-3 text-sm font-bold text-ink-700">Go to dashboard</Link>
          </div>
        </section>
      </PageContainer>
    </main>
  );
}
