import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Navigate, useNavigate, useParams } from "react-router";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { MediaPreview } from "@/components/facefit/interview/MediaPreview";
import { useAuth } from "@/auth/auth-context";
import { createIdempotencyKey, poll } from "@/api/polling";
import { createClientEvent, sendClientEvent } from "@/api/telemetry";
import {
  createAnswerFormData,
  isInterviewComplete,
  isInterviewQuestion,
  type CurrentQuestion,
  type InterviewQuestion,
  type InterviewAnswer,
  type PlaybackAccess,
} from "@/api/live";
import { useMediaDevices } from "@/hooks/useMediaDevices";
import { useAnswerRecorder } from "@/hooks/useAnswerRecorder";
import { useVoiceActivityStop } from "@/hooks/useVoiceActivityStop";
import {
  getAnswerOutbox,
  removeAnswerOutbox,
  saveAnswerOutbox,
  type AnswerOutboxRecord,
} from "@/lib/answer-outbox";

export default function SessionLiveApiPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { request, upload } = useAuth();
  const {
    stream,
    status: mediaStatus,
    message: mediaMessage,
    start,
  } = useMediaDevices();
  const {
    reset: resetRecorder,
    stop: stopRecorder,
    ...recorder
  } = useAnswerRecorder(stream);
  const [question, setQuestion] = useState<CurrentQuestion | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<
    "loading" | "answering" | "submitting" | "complete" | "error"
  >("loading");
  const [message, setMessage] = useState("");
  const [savedAnswer, setSavedAnswer] = useState<AnswerOutboxRecord | null>(
    null,
  );
  const answerKeyRef = useRef<string | null>(null);
  const endedByRef = useRef<"USER_BUTTON" | "SPACE_KEY" | "SILENCE_CONFIRMED">(
    "USER_BUTTON",
  );
  const completionKeyRef = useRef<string | null>(null);
  const stopForSilence = useCallback(() => {
    endedByRef.current = "SILENCE_CONFIRMED";
    stopRecorder();
  }, [stopRecorder]);
  const vadCountdown = useVoiceActivityStop(
    stream,
    recorder.state === "recording",
    stopForSilence,
  );

  const loadPlaybackAccess = useCallback(
    async (nextQuestion: InterviewQuestion) => {
      if (!sessionId || nextQuestion.characterMediaStatus !== "READY") {
        setVideoUrl(null);
        return;
      }
      const access = await request<PlaybackAccess>(
        `/api/v1/interview-sessions/${sessionId}/questions/${nextQuestion.questionId}/character-media-access`,
        { method: "POST" },
      );
      setVideoUrl(access.playbackUrl);
    },
    [request, sessionId],
  );

  useEffect(() => {
    if (!sessionId || !question || !isInterviewQuestion(question)) return;
    let active = true;
    void getAnswerOutbox(sessionId, question.questionId)
      .then((record) => {
        if (!active || !record) return;
        setSavedAnswer(record);
        setMessage("A saved answer is ready to retry.");
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [question, sessionId]);

  useEffect(() => {
    if (
      !sessionId ||
      !question ||
      !isInterviewQuestion(question) ||
      recorder.state !== "ready" ||
      !recorder.blob
    )
      return;
    const idempotencyKey = answerKeyRef.current ?? createIdempotencyKey();
    answerKeyRef.current = idempotencyKey;
    const record: AnswerOutboxRecord = {
      idempotencyKey,
      sessionId,
      questionId: question.questionId,
      blob: recorder.blob,
      recordedDurationMs: recorder.durationMs,
      endedBy: endedByRef.current,
      createdAt: new Date().toISOString(),
    };
    void saveAnswerOutbox(record)
      .then(() => setSavedAnswer(record))
      .catch(() => undefined);
  }, [question, recorder.blob, recorder.durationMs, recorder.state, sessionId]);

  const loadQuestion = useCallback(async () => {
    if (!sessionId) return;
    setStatus("loading");
    const nextQuestion = await poll<CurrentQuestion>({
      load: () =>
        request<CurrentQuestion>(
          `/api/v1/interview-sessions/${sessionId}/questions/current`,
        ),
      shouldContinue: (value) =>
        !isInterviewQuestion(value) && !isInterviewComplete(value),
      retryAfterMs: (value) =>
        "retryAfterSec" in value && typeof value.retryAfterSec === "number"
          ? value.retryAfterSec * 1000
          : null,
      intervalMs: 2000,
      maxWaitMs: 60000,
    });
    setQuestion(nextQuestion);
    if (isInterviewComplete(nextQuestion)) {
      setStatus("complete");
      return;
    }
    if (!isInterviewQuestion(nextQuestion)) {
      setStatus("error");
      setMessage(
        "질문을 준비하는 시간이 길어지고 있어요. 잠시 뒤 다시 시도해 주세요.",
      );
      return;
    }
    await loadPlaybackAccess(nextQuestion);
    resetRecorder();
    setStatus("answering");
  }, [loadPlaybackAccess, request, resetRecorder, sessionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void start();
      void loadQuestion().catch((error) => {
        setStatus("error");
        setMessage(
          error instanceof Error
            ? error.message
            : "면접 질문을 불러오지 못했습니다.",
        );
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadQuestion, start]);

  const submitAnswer = async (queuedAnswer?: AnswerOutboxRecord) => {
    if (
      !sessionId ||
      !question ||
      !isInterviewQuestion(question) ||
      (!queuedAnswer && (!recorder.blob || recorder.state !== "ready")) ||
      (queuedAnswer && queuedAnswer.questionId !== question.questionId) ||
      status === "submitting"
    )
      return;
    setStatus("submitting");
    try {
      const idempotencyKey =
        queuedAnswer?.idempotencyKey ??
        answerKeyRef.current ??
        createIdempotencyKey();
      answerKeyRef.current = idempotencyKey;
      const submittedEndedBy = queuedAnswer?.endedBy ?? endedByRef.current;
      const blob = queuedAnswer?.blob ?? recorder.blob;
      const recordedDurationMs =
        queuedAnswer?.recordedDurationMs ?? recorder.durationMs;
      if (!blob) return;
      const answer = await upload<InterviewAnswer>(
        `/api/v1/interview-sessions/${sessionId}/answers`,
        {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey },
          formData: createAnswerFormData(
            question.questionId,
            blob,
            recordedDurationMs,
            submittedEndedBy,
          ),
        },
      );
      await poll<InterviewAnswer>({
        load: () =>
          request<InterviewAnswer>(
            `/api/v1/interview-answers/${answer.answerId}`,
          ),
        shouldContinue: (value) => value.nextQuestionStatus === "WAITING",
        intervalMs: 2000,
        maxWaitMs: 30000,
      });
      await removeAnswerOutbox(idempotencyKey);
      setSavedAnswer(null);
      answerKeyRef.current = null;
      endedByRef.current = "USER_BUTTON";
      void sendClientEvent(
        request,
        createClientEvent("answer_upload_succeeded", sessionId, {
          answerId: answer.answerId,
        }),
      );
      await loadQuestion();
    } catch (error) {
      void sendClientEvent(
        request,
        createClientEvent("answer_upload_failed", sessionId, {
          errorCode: error instanceof Error ? error.name : "UNKNOWN",
        }),
      );
      setStatus("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "답변을 저장하지 못했습니다. 다시 시도해 주세요.",
      );
    }
  };

  const finish = async (completionType: "NORMAL" | "USER_INTERRUPTED") => {
    if (!sessionId) return;
    completionKeyRef.current ??= createIdempotencyKey();
    try {
      await request(`/api/v1/interview-sessions/${sessionId}/completion`, {
        method: "POST",
        headers: { "Idempotency-Key": completionKeyRef.current },
        body: { completionType },
      });
      navigate(`/sessions/${sessionId}/analysis`, { replace: true });
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "면접 종료를 저장하지 못했습니다.",
      );
    }
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.code !== "Space" ||
        event.repeat ||
        recorder.state !== "recording"
      )
        return;
      const target = event.target as HTMLElement | null;
      if (
        target?.matches("input, textarea, select, button") ||
        target?.isContentEditable
      )
        return;
      event.preventDefault();
      endedByRef.current = "SPACE_KEY";
      stopRecorder();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [recorder.state, stopRecorder]);

  if (!sessionId) return <Navigate to="/onboarding" replace />;

  return (
    <main className="min-h-screen bg-[#18221e] text-white">
      <PageContainer size="wide" className="py-5">
        <header className="flex items-center justify-between">
          <p className="text-sm font-bold">AI 면접 진행</p>
          <button
            type="button"
            onClick={() => void finish("USER_INTERRUPTED")}
            className="rounded-lg border border-white/20 px-4 py-2 text-sm"
          >
            면접 중단
          </button>
        </header>
        <section className="mt-5 grid gap-5 lg:grid-cols-[1.8fr_1fr]">
          <div className="relative min-h-[360px] overflow-hidden rounded-2xl bg-[#0e1a17]">
            <img
              src="/images/interviewer-hr.png"
              alt="AI 면접관"
              className="absolute inset-0 size-full object-cover"
            />
            {videoUrl ? (
              <video
                src={videoUrl}
                autoPlay
                playsInline
                controls
                onError={() => {
                  if (question && isInterviewQuestion(question))
                    void loadPlaybackAccess(question).catch(() =>
                      setVideoUrl(null),
                    );
                }}
                className="absolute inset-0 size-full object-cover"
              />
            ) : null}
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 p-7">
              <p className="text-xs font-bold tracking-widest text-[#b4d3bd]">
                {question && isInterviewQuestion(question)
                  ? `${question.questionKind} QUESTION ${question.turnOrder}`
                  : "QUESTION"}
              </p>
              <h1 className="mt-3 text-xl font-bold leading-8">
                {question && isInterviewQuestion(question)
                  ? question.text
                  : status === "loading"
                    ? "질문을 준비하고 있어요."
                    : "면접을 계속할 수 없습니다."}
              </h1>
            </div>
          </div>
          <aside className="overflow-hidden rounded-2xl bg-[#20372b] p-5">
            <p className="text-sm font-bold">내 카메라</p>
            <div className="mt-4 aspect-video overflow-hidden rounded-xl bg-black/30">
              <MediaPreview stream={stream} label="내 카메라 미리보기" />
            </div>
            <p role="status" className="mt-4 text-sm text-white/70">
              {mediaStatus === "ready"
                ? "카메라와 마이크가 연결되었습니다."
                : mediaMessage || "장치를 연결하고 있어요."}
            </p>
          </aside>
        </section>
        <section className="mt-5 rounded-2xl bg-[#20372b] p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-bold">답변 녹화</p>
              <p className="mt-1 text-sm text-white/65">
                {recorder.message ||
                  (recorder.state === "recording"
                    ? "녹화 중입니다. Space 또는 완료 버튼으로 멈출 수 있어요."
                    : recorder.state === "ready"
                      ? `${Math.ceil(recorder.durationMs / 1000)}초 답변을 저장할 준비가 됐어요.`
                      : "녹화를 시작한 뒤 답변을 진행해 주세요.")}
              </p>
              {vadCountdown ? (
                <p
                  role="status"
                  className="mt-2 text-sm font-bold text-[#ffc49d]"
                >
                  Silence detected. Recording stops in {vadCountdown}.
                </p>
              ) : null}
            </div>
            <div className="flex gap-2">
              {recorder.state !== "recording" && recorder.state !== "ready" ? (
                <button
                  type="button"
                  onClick={recorder.start}
                  disabled={status !== "answering"}
                  className="rounded-xl bg-white px-5 py-3 text-sm font-bold text-[#20372b]"
                >
                  <Play size={15} className="mr-1 inline" />
                  답변 녹화
                </button>
              ) : null}
              {recorder.state === "recording" ? (
                <button
                  type="button"
                  onClick={stopRecorder}
                  className="rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold"
                >
                  <Pause size={15} className="mr-1 inline" />
                  답변 완료
                </button>
              ) : null}
              {recorder.state === "ready" ? (
                <button
                  type="button"
                  onClick={() => void submitAnswer()}
                  disabled={status === "submitting"}
                  className="rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold"
                >
                  {status === "submitting" ? "저장 중" : "답변 제출"}
                </button>
              ) : null}
              {savedAnswer && recorder.state !== "ready" ? (
                <button
                  type="button"
                  onClick={() => void submitAnswer(savedAnswer)}
                  disabled={status === "submitting"}
                  className="rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold"
                >
                  {status === "submitting" ? "저장 중" : "저장된 답변 재전송"}
                </button>
              ) : null}
            </div>
          </div>
          {message ? (
            <p
              role="alert"
              className="mt-4 rounded-xl border border-sunset-300/30 bg-black/15 p-3 text-sm text-[#ffc49d]"
            >
              {message}
            </p>
          ) : null}
        </section>
        {status === "complete" ? (
          <section className="mt-5 rounded-2xl bg-white p-6 text-ink-900">
            <h2 className="text-xl font-bold">모든 질문 답변이 완료됐어요.</h2>
            <p className="mt-2 text-sm text-ink-600">
              분석을 시작하면 완료 뒤 리포트에서 결과를 확인할 수 있어요.
            </p>
            <button
              type="button"
              onClick={() => void finish("NORMAL")}
              className="mt-5 rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white"
            >
              면접 종료 및 분석 시작
            </button>
          </section>
        ) : null}
      </PageContainer>
    </main>
  );
}
