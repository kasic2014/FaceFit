# Stage 26 speech characteristics

Stage 26 combines the four validated Stage 24 answer WAVs with the corresponding Stage 25 transcript and word timestamps. It reports physical and timing measurements only. It does not score speaking ability, infer confidence or emotion, classify personality or gender, or evaluate answer content.

## Command and inputs

```powershell
python scripts\analyze_speech_session.py --session-id SES_000001
```

Optional flags are `--force-rebuild`, `--output-root`, and `--profile stage26-measurement-v1`. Arbitrary audio, transcript, video, and participant paths are not accepted. Input is resolved only from ready Stage 24 and Stage 25 manifests, with WAV and transcript SHA-256 verification.

## Measurement profile

The profile version is `1.0.0`. Timestamp pause views are emitted at 250, 500, 1000, and 2000 ms. They are overlapping technical query views, not approved evaluation thresholds. `thresholdPurpose=TECHNICAL_VIEW_ONLY` and `scoringApproved=false` are recorded.

PCM energy uses 25 ms frames and a 10 ms hop. The acoustic silence-candidate threshold is the answer's finite frame-RMS P90 minus 20 dB, bounded to -80 through -35 dBFS. This adaptive threshold creates candidate regions only; it does not label speech as normal or abnormal. No gain, normalization, compression, denoising, or source modification is performed.

Pitch uses 40 ms frames, a 10 ms hop, numpy FFT autocorrelation, a 50–500 Hz technical search range, and correlation/energy gating. Unvoiced frames are excluded rather than represented as 0 Hz. F0 values describe physical periodicity and do not infer gender, emotion, confidence, nervousness, or personality.

`f0RangeHz` is maximum F0 minus minimum F0. The robust central range is reported separately as `p10P90RangeHz`.

Korean filler candidates use the versioned `ko-filler-candidates` lexicon. Matches are candidates requiring human review, not definitive filler labels, corrections, deletions, or score deductions.

## Output and idempotency

Ignored output under `data/output/speech_characteristics/<sessionId>/` contains four answer JSON documents, a session manifest, strict validation, a technical report, and a manual-review packet. Contracts exclude participant IDs, source paths, original media names, scores, grades, and pass probabilities.

The fingerprint covers Stage 24 WAV hashes, Stage 25 transcript hashes, profile version and all frame, pause, pitch, and lexicon settings. Unchanged verified output returns `reused: true`; forced analysis is built and validated in a temporary directory before atomic replacement.
