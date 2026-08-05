import { useEffect, useRef } from "react";
import { CameraOff } from "lucide-react";

type MediaPreviewProps = {
  stream: MediaStream | null;
  className?: string;
  mirrored?: boolean;
  label?: string;
};

export function MediaPreview({ stream, className = "", mirrored = true, label = "카메라 미리보기" }: MediaPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    if (stream) void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  if (!stream) {
    return <div className={`grid place-items-center bg-[#1c2b26] text-center text-sm text-white/70 ${className}`}><span><CameraOff className="mx-auto mb-2" size={20} />카메라 연결을 기다리고 있어요.</span></div>;
  }

  return <video ref={videoRef} aria-label={label} autoPlay muted playsInline className={`size-full object-cover ${mirrored ? "-scale-x-100" : ""} ${className}`} />;
}
