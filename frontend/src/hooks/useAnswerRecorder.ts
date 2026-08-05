import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "ready" | "error";

// ponytail: AGENTS.md caps answers at 200MB/300s server-side. These are the same numbers,
// enforced client-side so a rejected upload doesn't waste a full recording. Not a product-facing limit.
const preferredMimeTypes = ["video/mp4;codecs=avc1,mp4a", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
const MAX_DURATION_MS = 300_000;
const MAX_BYTES = 200 * 1024 * 1024;

export function selectMimeType() {
  return preferredMimeTypes.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? "";
}

export function useAnswerRecorder(stream: MediaStream | null) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const bytesRef = useRef(0);
  const limitTimerRef = useRef<number | null>(null);
  const [state, setState] = useState<RecorderState>("idle");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [message, setMessage] = useState("");

  const reset = useCallback(() => {
    setBlob(null);
    setDurationMs(0);
    setMessage("");
    setState("idle");
  }, []);

  const clearLimitTimer = useCallback(() => {
    if (limitTimerRef.current !== null) {
      window.clearTimeout(limitTimerRef.current);
      limitTimerRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const start = useCallback(() => {
    if (!stream || stream.getVideoTracks().every((track) => track.readyState !== "live" || !track.enabled) || stream.getAudioTracks().every((track) => track.readyState !== "live" || !track.enabled)) {
      setMessage("카메라와 마이크가 모두 연결된 뒤 답변을 녹화할 수 있어요.");
      setState("error");
      return;
    }
    if (!window.MediaRecorder) {
      setMessage("이 브라우저는 면접 녹화를 지원하지 않습니다.");
      setState("error");
      return;
    }

    const mimeType = selectMimeType();
    if (!mimeType) {
      setMessage("이 브라우저는 지원하는 녹화 형식이 없습니다. 최신 Chrome 또는 Safari를 사용해 주세요.");
      setState("error");
      return;
    }

    chunksRef.current = [];
    bytesRef.current = 0;
    setBlob(null);
    setDurationMs(0);
    setMessage("");
    try {
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size === 0) return;
        chunksRef.current.push(event.data);
        bytesRef.current += event.data.size;
        if (bytesRef.current >= MAX_BYTES) recorder.stop();
      };
      recorder.onstop = () => {
        clearLimitTimer();
        const finalMimeType = recorder.mimeType || mimeType;
        setBlob(new Blob(chunksRef.current, { type: finalMimeType }));
        setDurationMs(Math.max(0, Date.now() - (startedAtRef.current ?? Date.now())));
        setState("ready");
      };
      recorder.onerror = () => {
        clearLimitTimer();
        setMessage("답변 녹화를 계속할 수 없습니다. 장치를 확인해 주세요.");
        setState("error");
      };
      startedAtRef.current = Date.now();
      recorder.start(1000);
      limitTimerRef.current = window.setTimeout(() => stop(), MAX_DURATION_MS);
      setState("recording");
    } catch {
      setMessage("답변 녹화를 시작하지 못했습니다. 장치를 다시 연결해 주세요.");
      setState("error");
    }
  }, [clearLimitTimer, stop, stream]);

  useEffect(() => () => {
    clearLimitTimer();
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, [clearLimitTimer]);

  return { state, blob, durationMs, message, start, stop, reset };
}
