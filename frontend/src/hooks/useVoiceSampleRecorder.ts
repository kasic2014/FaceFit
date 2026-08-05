import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceSampleRecorderState =
  | "idle"
  | "requesting"
  | "recording"
  | "ready"
  | "error";

// VOICE-001 accepts 15-60s samples. Same bounds enforced client-side so a too-short
// or too-long take is caught before the consent record and upload are created.
const preferredMimeTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
const MIN_DURATION_MS = 15_000;
const MAX_DURATION_MS = 60_000;

function selectMimeType() {
  return (
    preferredMimeTypes.find((mimeType) =>
      MediaRecorder.isTypeSupported(mimeType),
    ) ?? ""
  );
}

function extensionFor(mimeType: string) {
  return mimeType.includes("mp4") ? "m4a" : "webm";
}

export function useVoiceSampleRecorder() {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const limitTimerRef = useRef<number | null>(null);
  const [state, setState] = useState<VoiceSampleRecorderState>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [message, setMessage] = useState("");

  const clearLimitTimer = useCallback(() => {
    if (limitTimerRef.current !== null) {
      window.clearTimeout(limitTimerRef.current);
      limitTimerRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const reset = useCallback(() => {
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setFile(null);
    setDurationMs(0);
    setElapsedMs(0);
    setMessage("");
    setState("idle");
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
      setMessage("이 브라우저는 음성 녹음을 지원하지 않습니다.");
      setState("error");
      return;
    }
    const mimeType = selectMimeType();
    if (!mimeType) {
      setMessage(
        "이 브라우저는 지원하는 녹음 형식이 없습니다. 최신 Chrome 또는 Safari를 사용해 주세요.",
      );
      setState("error");
      return;
    }

    setState("requesting");
    setMessage("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      setPreviewUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
      setFile(null);
      setDurationMs(0);
      setElapsedMs(0);

      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        clearLimitTimer();
        releaseStream();
        const finalMimeType = recorder.mimeType || mimeType;
        const recordedMs = Math.max(
          0,
          Date.now() - (startedAtRef.current ?? Date.now()),
        );
        const blob = new Blob(chunksRef.current, { type: finalMimeType });
        setDurationMs(recordedMs);
        if (recordedMs < MIN_DURATION_MS) {
          setMessage(
            `녹음이 너무 짧아요. 최소 ${MIN_DURATION_MS / 1000}초 이상 말해 주세요.`,
          );
          setState("error");
          return;
        }
        setFile(
          new File(
            [blob],
            `voice-sample.${extensionFor(finalMimeType)}`,
            { type: finalMimeType },
          ),
        );
        setPreviewUrl(URL.createObjectURL(blob));
        setState("ready");
      };
      recorder.onerror = () => {
        clearLimitTimer();
        releaseStream();
        setMessage("녹음을 계속할 수 없습니다. 마이크를 확인해 주세요.");
        setState("error");
      };
      startedAtRef.current = Date.now();
      recorder.start(1000);
      limitTimerRef.current = window.setTimeout(() => stop(), MAX_DURATION_MS);
      setState("recording");
    } catch {
      releaseStream();
      setMessage(
        "마이크 권한을 허용해야 녹음할 수 있어요. 브라우저 설정에서 허용한 뒤 다시 시도해 주세요.",
      );
      setState("error");
    }
  }, [clearLimitTimer, releaseStream, stop]);

  useEffect(() => {
    if (state !== "recording") return;
    const timer = window.setInterval(
      () => setElapsedMs(Date.now() - (startedAtRef.current ?? Date.now())),
      200,
    );
    return () => window.clearInterval(timer);
  }, [state]);

  useEffect(
    () => () => {
      clearLimitTimer();
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      releaseStream();
    },
    [clearLimitTimer, releaseStream],
  );

  return {
    state,
    file,
    previewUrl,
    durationMs,
    elapsedMs,
    message,
    maxDurationMs: MAX_DURATION_MS,
    minDurationMs: MIN_DURATION_MS,
    start,
    stop,
    reset,
  };
}
