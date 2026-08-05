import { useEffect, useState } from "react";

// FN-007 asks for a visible mic input check on the equipment screen. Same RMS read as
// useVoiceActivityStop, but reported continuously as a 0-1 level instead of driving auto-stop.
function getRms(analyser: AnalyserNode, data: Uint8Array<ArrayBuffer>) {
  analyser.getByteTimeDomainData(data);
  const sum = data.reduce((total, sample) => {
    const normalized = (sample - 128) / 128;
    return total + normalized * normalized;
  }, 0);
  return Math.sqrt(sum / data.length);
}

export function useMicLevel(stream: MediaStream | null) {
  const [level, setLevel] = useState(0);
  const active =
    !!stream &&
    stream
      .getAudioTracks()
      .some((track) => track.readyState === "live" && track.enabled);

  useEffect(() => {
    if (!active || !stream) return;

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const data: Uint8Array<ArrayBuffer> = new Uint8Array(analyser.fftSize);

    const timer = window.setInterval(() => {
      setLevel(Math.min(1, getRms(analyser, data) * 6));
    }, 100);

    return () => {
      window.clearInterval(timer);
      source.disconnect();
      void context.close();
    };
  }, [active, stream]);

  return active ? level : 0;
}
