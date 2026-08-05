import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { type ReportData, isReportData } from "@/api/analysis";
import { type MediaDeletion, type PlaybackAccess } from "@/api/privacy";
import { poll } from "@/api/polling";
import type { InterviewSession } from "@/api/setup";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { QuestionContextPanel } from "@/components/facefit/report/QuestionContextPanel";

const scoreLabels = {
  gaze: "Gaze",
  posture: "Posture",
  speech: "Speech",
  content: "Content",
} as const;

function getRetryAfterSec(value: unknown) {
  if (typeof value !== "object" || value === null || !("data" in value))
    return null;
  const data = value.data;
  if (typeof data !== "object" || data === null || !("retryAfterSec" in data))
    return null;
  return typeof data.retryAfterSec === "number" ? data.retryAfterSec : null;
}

export default function ReportApiPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { binary, request } = useAuth();
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioMessage, setAudioMessage] = useState("");
  const [mediaDeletion, setMediaDeletion] = useState<MediaDeletion | null>(
    null,
  );
  const [mediaDeletionError, setMediaDeletionError] = useState("");
  const [creatingPractice, setCreatingPractice] = useState(false);
  const [videoAccess, setVideoAccess] = useState<PlaybackAccess | null>(null);
  const [activeClip, setActiveClip] = useState<{
    answerId: string;
    startMs: number;
    endMs: number;
  } | null>(null);
  const audioElementRef = useRef<HTMLAudioElement>(null);
  const videoElementRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void poll({
        load: () =>
          request<ReportData | { status: "PROCESSING"; retryAfterSec: number }>(
            `/api/v1/interview-sessions/${sessionId}/report`,
            { signal: controller.signal },
          ),
        onValue: (value) => {
          if (active && isReportData(value)) setReportData(value);
        },
        shouldContinue: (value) => !isReportData(value),
        retryAfterMs: (value) =>
          isReportData(value) ? null : value.retryAfterSec * 1000,
        intervalMs: 3000,
        maxWaitMs: 10 * 60 * 1000,
        signal: controller.signal,
      }).catch((reason: unknown) => {
        if (
          !active ||
          (reason instanceof DOMException && reason.name === "AbortError")
        )
          return;
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load the report.",
        );
      });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request, sessionId]);

  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );

  const playImprovedAnswer = async (
    feedbackId: string,
    voiceType: "STANDARD" | "PERSONAL",
  ) => {
    if (!reportData) return;
    setAudioMessage("");
    try {
      const response = await binary(
        `/api/v1/reports/${reportData.report.reportId}/question-feedback/${feedbackId}/improved-answer-audio?voiceType=${voiceType}`,
      );
      if (response.status === 202) {
        setAudioMessage(
          `Audio is being prepared. Try again in ${getRetryAfterSec(await response.json()) ?? 3} seconds.`,
        );
        return;
      }
      const nextAudioUrl = URL.createObjectURL(await response.blob());
      setAudioUrl((currentUrl) => {
        if (currentUrl) URL.revokeObjectURL(currentUrl);
        return nextAudioUrl;
      });
      window.setTimeout(
        () => void audioElementRef.current?.play().catch(() => undefined),
        0,
      );
    } catch (reason) {
      setAudioMessage(
        reason instanceof Error
          ? reason.message
          : "Unable to play the improved answer.",
      );
    }
  };

  const requestAnswerMedia = async (
    answerId: string,
    startMs: number,
    endMs: number,
  ) => {
    try {
      const access = await request<PlaybackAccess>(
        `/api/v1/interview-answers/${answerId}/media-access`,
        { method: "POST", body: { startMs, endMs } },
      );
      setActiveClip({ answerId, startMs, endMs });
      setVideoAccess(access);
      window.setTimeout(() => {
        if (!videoElementRef.current) return;
        videoElementRef.current.currentTime = access.clipStartMs / 1000;
        void videoElementRef.current.play().catch(() => undefined);
      }, 0);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to play answer evidence.",
      );
    }
  };

  const deleteOriginalMedia = async () => {
    if (!sessionId || mediaDeletion) return;
    setMediaDeletionError("");
    try {
      const initial = await request<MediaDeletion>(
        `/api/v1/interview-sessions/${sessionId}/media`,
        { method: "DELETE", body: { scope: "ORIGINAL_MEDIA" } },
      );
      setMediaDeletion(initial);
      setMediaDeletion(
        await poll<MediaDeletion>({
          load: () =>
            request<MediaDeletion>(
              `/api/v1/interview-sessions/${sessionId}/media-deletion`,
            ),
          onValue: setMediaDeletion,
          shouldContinue: (value) =>
            value.status === "QUEUED" || value.status === "PROCESSING",
          intervalMs: 5000,
          maxWaitMs: 10 * 60 * 1000,
        }),
      );
    } catch (reason) {
      setMediaDeletionError(
        reason instanceof Error
          ? reason.message
          : "Unable to delete original media.",
      );
    }
  };

  const createPracticeSession = async () => {
    if (!sessionId || creatingPractice) return;
    setCreatingPractice(true);
    try {
      const nextSession = await request<InterviewSession>(
        `/api/v1/interview-sessions/${sessionId}/clone`,
        { method: "POST", body: {} },
      );
      navigate(`/equipment/${nextSession.sessionId}`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to create a practice session.",
      );
      setCreatingPractice(false);
    }
  };

  if (!sessionId) return <Navigate to="/dashboard" replace />;
  if (!reportData)
    return (
      <main className="min-h-screen bg-ivory-50">
        <PageContainer size="narrow" className="py-14">
          <section className="rounded-2xl border border-line-200 bg-white p-7">
            <h1 className="text-2xl font-bold text-ink-900">
              Report is being prepared
            </h1>
            <p className="mt-3 text-sm text-ink-600">
              {error ||
                "The report will appear automatically when generation finishes."}
            </p>
            <Link
              to={`/sessions/${sessionId}/analysis`}
              className="mt-6 inline-flex rounded-xl border border-line-300 px-5 py-3 text-sm font-bold text-ink-700"
            >
              View analysis status
            </Link>
          </section>
        </PageContainer>
      </main>
    );

  const { report } = reportData;
  return (
    <main className="min-h-screen bg-ivory-50 text-ink-900">
      <PageContainer size="wide" className="py-10">
        <p className="text-sm text-ink-500">
          Rubric {report.rubricVersion} -{" "}
          {new Date(report.generatedAt).toLocaleDateString()}
        </p>
        <h1 className="mt-3 text-3xl font-bold">Interview report</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-ink-600">
          {report.disclaimer}
        </p>
        <section className="mt-7 rounded-2xl bg-moss-900 p-7 text-white md:flex md:items-center md:gap-8">
          <div className="grid size-28 place-items-center rounded-full border-8 border-moss-300 text-center">
            <strong className="text-4xl">
              {report.overallScore.toFixed(1)}
            </strong>
            <span className="text-xs text-white/70">Overall score</span>
          </div>
          <div className="mt-5 md:mt-0">
            <h2 className="text-xl font-bold">
              Evidence-based practice guidance
            </h2>
            <p className="mt-2 text-sm leading-6 text-white/75">
              Scores are derived from completed interview answers. They are not
              a hiring decision.
            </p>
            <button
              type="button"
              onClick={() => void createPracticeSession()}
              disabled={creatingPractice}
              className="mt-4 rounded-lg bg-white px-4 py-2 text-sm font-bold text-moss-900 disabled:opacity-60"
            >
              {creatingPractice ? "Creating practice" : "Practice again"}
            </button>
          </div>
        </section>
        <section className="mt-7 grid gap-4 md:grid-cols-2">
          {Object.entries(report.scores).map(([axis, score]) => (
            <article
              key={axis}
              className="rounded-2xl border border-line-200 bg-white p-6"
            >
              <div className="flex items-center justify-between">
                <h2 className="font-bold">
                  {scoreLabels[axis as keyof typeof scoreLabels]}
                </h2>
                <strong className="text-moss-900">
                  {score === null ? "Not assessed" : `${score.toFixed(1)}/100`}
                </strong>
              </div>
              {score === null ? (
                <p className="mt-4 text-sm text-ink-600">
                  Speech analysis was not included in this interview.
                </p>
              ) : (
                <ScoreBlocks score={score} label={axis} />
              )}
            </article>
          ))}
        </section>
        <section className="mt-7 grid gap-5 lg:grid-cols-2">
          <article className="rounded-2xl border border-line-200 bg-white p-6">
            <h2 className="text-lg font-bold">Strengths</h2>
            <div className="mt-4 space-y-4">
              {report.strengths.map((strength) => (
                <div key={strength.title}>
                  <p className="font-bold text-moss-800">{strength.title}</p>
                  <p className="mt-1 text-sm leading-6 text-ink-600">
                    {strength.description}
                  </p>
                </div>
              ))}
            </div>
          </article>
          <article className="rounded-2xl border border-line-200 bg-white p-6">
            <h2 className="text-lg font-bold">Practice priorities</h2>
            <ol className="mt-4 space-y-4">
              {[...report.improvements]
                .sort((left, right) => left.priority - right.priority)
                .map((improvement) => (
                  <li key={improvement.improvementId}>
                    <p className="font-bold text-moss-800">
                      {improvement.priority}. {improvement.title}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-ink-600">
                      {improvement.practice}
                    </p>
                  </li>
                ))}
            </ol>
          </article>
        </section>
        <section className="mt-7 space-y-4">
          <h2 className="text-xl font-bold">Question feedback</h2>
          {report.questionFeedback.map((feedback) => (
            <article
              key={feedback.feedbackId}
              className="rounded-2xl border border-line-200 bg-white p-6"
            >
              <p className="text-sm font-bold text-sunset-700">
                QUESTION {String(feedback.order).padStart(2, "0")} -{" "}
                {feedback.score.toFixed(1)}/100
              </p>
              <h3 className="mt-3 text-lg font-bold">{feedback.question}</h3>
              <p className="mt-3 text-sm leading-6 text-ink-600">
                {feedback.answerSummary}
              </p>
              <p className="mt-4 text-sm font-semibold text-moss-800">
                Suggested answer
              </p>
              <p className="mt-1 text-sm leading-6 text-ink-700">
                {feedback.improvedAnswerText}
              </p>
              <div className="mt-4 space-y-2">
                {feedback.evidence.map((evidence) => (
                  <div
                    key={`${evidence.label}-${evidence.value}`}
                    className="rounded-lg bg-ivory-100 p-3 text-sm text-ink-700"
                  >
                    <strong>{evidence.label}: </strong>
                    {evidence.value}
                    {evidence.startMs !== null && evidence.endMs !== null ? (
                      <button
                        type="button"
                        onClick={() =>
                          void requestAnswerMedia(
                            feedback.answerId,
                            evidence.startMs as number,
                            evidence.endMs as number,
                          )
                        }
                        className="ml-3 font-bold text-moss-800 underline"
                      >
                        Play video evidence
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {feedback.audioAvailability.standard === "READY" ? (
                  <button
                    type="button"
                    onClick={() =>
                      void playImprovedAnswer(feedback.feedbackId, "STANDARD")
                    }
                    className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700"
                  >
                    Play standard audio
                  </button>
                ) : null}
                {feedback.audioAvailability.personal === "READY" ? (
                  <button
                    type="button"
                    onClick={() =>
                      void playImprovedAnswer(feedback.feedbackId, "PERSONAL")
                    }
                    className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700"
                  >
                    Play personal audio
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </section>
        <QuestionContextPanel sessionId={sessionId} />
        <section className="mt-7 rounded-2xl border border-line-200 bg-white p-6">
          <h2 className="text-lg font-bold">Original interview media</h2>
          <p className="mt-2 text-sm leading-6 text-ink-600">
            Deleting original video and audio keeps your report and scores, but
            removes playback access.
          </p>
          {mediaDeletion ? (
            <p role="status" className="mt-4 text-sm font-bold text-moss-800">
              Deletion status: {mediaDeletion.status}
            </p>
          ) : (
            <button
              type="button"
              onClick={() => void deleteOriginalMedia()}
              className="mt-4 rounded-lg border border-sunset-300 px-4 py-2 text-sm font-bold text-sunset-700"
            >
              Delete original media
            </button>
          )}
          {mediaDeletionError ? (
            <p role="alert" className="mt-3 text-sm text-sunset-700">
              {mediaDeletionError}
            </p>
          ) : null}
        </section>
        {videoAccess && activeClip ? (
          <section className="mt-7 rounded-2xl border border-line-200 bg-white p-6">
            <h2 className="text-lg font-bold">Answer evidence</h2>
            <video
              ref={videoElementRef}
              src={videoAccess.playbackUrl}
              controls
              playsInline
              onTimeUpdate={() => {
                if (
                  videoElementRef.current &&
                  videoElementRef.current.currentTime >= activeClip.endMs / 1000
                )
                  videoElementRef.current.pause();
              }}
              onError={() =>
                void requestAnswerMedia(
                  activeClip.answerId,
                  activeClip.startMs,
                  activeClip.endMs,
                )
              }
              className="mt-4 w-full rounded-xl bg-black"
            />
          </section>
        ) : null}
        {audioMessage ? (
          <p
            role="status"
            className="mt-5 rounded-xl bg-ivory-100 p-4 text-sm text-ink-700"
          >
            {audioMessage}
          </p>
        ) : null}
        {audioUrl ? (
          <audio
            ref={audioElementRef}
            src={audioUrl}
            controls
            className="mt-5 w-full"
          />
        ) : null}
        {error ? (
          <p role="alert" className="mt-5 text-sm text-sunset-700">
            {error}
          </p>
        ) : null}
      </PageContainer>
    </main>
  );
}

function ScoreBlocks({ score, label }: { score: number; label: string }) {
  return (
    <div
      className="mt-4 grid grid-cols-10 gap-1"
      aria-label={`${label} ${score.toFixed(1)} out of 100`}
    >
      {Array.from({ length: 10 }, (_, index) => (
        <span
          key={index}
          className={
            index < Math.round(score / 10)
              ? "h-2 rounded-full bg-moss-700"
              : "h-2 rounded-full bg-ivory-200"
          }
        />
      ))}
    </div>
  );
}
