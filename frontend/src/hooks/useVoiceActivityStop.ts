import { useEffect, useState } from "react";

const guardMs = 3000;
const silenceMs = 2000;
const countdownMs = 1000;
const silenceThreshold = 0.015;

function getRms(analyser: AnalyserNode, data: Uint8Array<ArrayBuffer>) {
  analyser.getByteTimeDomainData(data);
  const sum = data.reduce((total, sample) => {
    const normalized = (sample - 128) / 128;
    return total + normalized * normalized;
  }, 0);
  return Math.sqrt(sum / data.length);
}

export function useVoiceActivityStop(stream: MediaStream | null, active: boolean, onAutoStop: () => void) {
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (!stream || !active || stream.getAudioTracks().every((track) => track.readyState !== "live" || !track.enabled)) {
      return;
    }

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const data: Uint8Array<ArrayBuffer> = new Uint8Array(analyser.fftSize);
    const startedAt = Date.now();
    let silenceStartedAt: number | null = null;
    let countdownStartedAt: number | null = null;
    let completed = false;

    const timer = window.setInterval(() => {
      const now = Date.now();
      if (now - startedAt < guardMs) return;
      if (getRms(analyser, data) >= silenceThreshold) {
        silenceStartedAt = null;
        countdownStartedAt = null;
        setCountdown(null);
        return;
      }
      silenceStartedAt ??= now;
      if (now - silenceStartedAt < silenceMs) return;
      countdownStartedAt ??= now;
      const remainingMs = countdownMs - (now - countdownStartedAt);
      if (remainingMs > 0) {
        setCountdown(Math.ceil(remainingMs / 1000));
        return;
      }
      if (!completed) {
        completed = true;
        setCountdown(null);
        onAutoStop();
      }
    }, 100);

    return () => {
      window.clearInterval(timer);
      source.disconnect();
      void context.close();
    };
  }, [active, onAutoStop, stream]);

  return active ? countdown : null;
}
