import { useCallback, useEffect, useRef, useState } from "react";

export type MediaDeviceStatus = "idle" | "requesting" | "ready" | "denied" | "unavailable" | "busy" | "unsupported" | "disconnected" | "error";
export type MediaDeviceKind = "videoinput" | "audioinput";

export type MediaDeviceOption = {
  deviceId: string;
  groupId: string;
  kind: MediaDeviceKind;
  label: string;
};

type MediaSelection = {
  cameraId?: string;
  microphoneId?: string;
};

type MediaFailure = {
  status: Exclude<MediaDeviceStatus, "idle" | "requesting" | "ready">;
  message: string;
};

const fallbackLabel: Record<MediaDeviceKind, string> = {
  videoinput: "카메라",
  audioinput: "마이크",
};

function hasMediaSupport() {
  const mediaDevices = typeof navigator === "undefined" ? undefined : navigator.mediaDevices as Partial<MediaDevices>;
  return typeof mediaDevices?.getUserMedia === "function";
}

function toFailure(error: unknown): MediaFailure {
  if (!(error instanceof DOMException)) return { status: "error", message: "장치를 시작하지 못했습니다. 잠시 후 다시 시도해 주세요." };
  if (error.name === "NotAllowedError" || error.name === "SecurityError") return { status: "denied", message: "카메라와 마이크 권한이 필요합니다. 브라우저 주소창 설정에서 허용한 뒤 다시 시도해 주세요." };
  if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") return { status: "unavailable", message: "사용 가능한 카메라 또는 마이크를 찾지 못했습니다. 장치 연결을 확인해 주세요." };
  if (error.name === "NotReadableError" || error.name === "TrackStartError") return { status: "busy", message: "다른 앱이 카메라 또는 마이크를 사용 중입니다. 해당 앱을 닫은 뒤 다시 시도해 주세요." };
  if (error.name === "OverconstrainedError") return { status: "unavailable", message: "선택한 장치를 사용할 수 없습니다. 다른 장치를 선택해 주세요." };
  return { status: "error", message: "장치 접근 중 오류가 발생했습니다. 다시 시도해 주세요." };
}

export function useMediaDevices() {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<MediaDeviceStatus>(() => hasMediaSupport() ? "idle" : "unsupported");
  const [message, setMessage] = useState("");
  const [cameras, setCameras] = useState<MediaDeviceOption[]>([]);
  const [microphones, setMicrophones] = useState<MediaDeviceOption[]>([]);
  const [selection, setSelection] = useState<MediaSelection>({});
  const streamRef = useRef<MediaStream | null>(null);
  const requestIdRef = useRef(0);

  const stop = useCallback(() => {
    requestIdRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
  }, []);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const toOption = (device: MediaDeviceInfo): MediaDeviceOption => ({
      deviceId: device.deviceId,
      groupId: device.groupId,
      kind: device.kind as MediaDeviceKind,
      label: device.label || fallbackLabel[device.kind as MediaDeviceKind],
    });
    setCameras(devices.filter((device) => device.kind === "videoinput").map(toOption));
    setMicrophones(devices.filter((device) => device.kind === "audioinput").map(toOption));
  }, []);

  const start = useCallback(async (nextSelection: MediaSelection = selection) => {
    if (!hasMediaSupport()) {
      setStatus("unsupported");
      setMessage("이 브라우저는 카메라와 마이크 접근을 지원하지 않습니다.");
      return;
    }

    stop();
    const requestId = requestIdRef.current;
    setStatus("requesting");
    setMessage("");
    try {
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: nextSelection.cameraId ? { deviceId: { exact: nextSelection.cameraId } } : true,
        audio: nextSelection.microphoneId ? { deviceId: { exact: nextSelection.microphoneId } } : true,
      });
      if (requestId !== requestIdRef.current) {
        nextStream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = nextStream;
      setStream(nextStream);
      setSelection(nextSelection);
      setStatus("ready");
      await refreshDevices();
      nextStream.getTracks().forEach((track) => {
        track.addEventListener("ended", () => {
          if (streamRef.current === nextStream) {
            setStatus("disconnected");
            setMessage("카메라 또는 마이크 연결이 끊겼습니다. 장치를 확인한 뒤 다시 연결해 주세요.");
          }
        }, { once: true });
      });
    } catch (error) {
      if (requestId !== requestIdRef.current) return;
      const failure = toFailure(error);
      setStatus(failure.status);
      setMessage(failure.message);
    }
  }, [refreshDevices, selection, stop]);

  const selectCamera = useCallback((cameraId: string) => start({ ...selection, cameraId }), [selection, start]);
  const selectMicrophone = useCallback((microphoneId: string) => start({ ...selection, microphoneId }), [selection, start]);

  useEffect(() => {
    const onDeviceChange = () => {
      void refreshDevices();
    };
    navigator.mediaDevices?.addEventListener("devicechange", onDeviceChange);
    return () => {
      navigator.mediaDevices?.removeEventListener("devicechange", onDeviceChange);
      stop();
    };
  }, [refreshDevices, stop]);

  return { stream, status, message, cameras, microphones, selection, start, stop, refreshDevices, selectCamera, selectMicrophone };
}
