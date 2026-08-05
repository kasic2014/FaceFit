import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "ready" | "error";

const preferredMimeTypes = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];

function selectMimeType() {
  return preferredMimeTypes.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? "";
}

export function useAnswerRecorder(stream: MediaStream | null) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
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
    chunksRef.current = [];
    setBlob(null);
    setDurationMs(0);
    setMessage("");
    try {
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const finalMimeType = recorder.mimeType || "video/webm";
        setBlob(new Blob(chunksRef.current, { type: finalMimeType }));
        setDurationMs(Math.max(0, Date.now() - (startedAtRef.current ?? Date.now())));
        setState("ready");
      };
      recorder.onerror = () => {
        setMessage("답변 녹화를 계속할 수 없습니다. 장치를 확인해 주세요.");
        setState("error");
      };
      startedAtRef.current = Date.now();
      recorder.start(1000);
      setState("recording");
    } catch {
      setMessage("답변 녹화를 시작하지 못했습니다. 장치를 다시 연결해 주세요.");
      setState("error");
    }
  }, [stream]);

  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  return { state, blob, durationMs, message, start, stop, reset };
}
