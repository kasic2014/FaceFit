# STT audio preprocessing

Stage 24 turns the audio stream of a canonical Vision Session into deterministic
STT input files. It does not run Faster-Whisper and does not evaluate speech.

Run from `ai-server/analysis-server` with the existing analysis environment:

```powershell
& $analysisPython scripts\build_stt_audio_preprocessing.py --session-id SES_000001
```

The CLI intentionally accepts no video path or participant identifier. It resolves
the Stage 15 canonical `metadata.json`, consent, and media triplet by Session ID.
Optional controls are `--force-rebuild`, `--output-root`, and `--ffmpeg-path`.

Output is written under `data/output/stt_preprocessing/<SESSION_ID>/`. The source
and each interval use WAV/PCM S16LE/16 kHz/mono. Intervals follow `[startMs,endMs)`;
both boundaries use `floor(milliseconds * 16000 / 1000)`, with no padding.
Interval output duration allows only the 1 ms integer-representation tolerance.
Decoded source duration is cross-checked against container duration with a 50 ms
technical tolerance; a larger difference is reported as `DURATION_MISMATCH`.

FFmpeg is preferred when its executable can be resolved. The installed PyAV
runtime is a deterministic fallback and is also used for media stream inspection.
If a sibling `ffprobe` is available it provides a cross-check only.

Repeated execution reuses a complete result only when the input media SHA-256 and
interval contract SHA-256 match and all declared WAV hashes still validate.
`--force-rebuild` stages a complete replacement before atomically swapping it in.
No source media, generated WAV, or output manifest is intended for Git.
