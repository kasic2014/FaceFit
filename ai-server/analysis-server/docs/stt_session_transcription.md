# Faster-Whisper session transcription

Stage 25 transcribes only the four answer WAVs produced and validated by Stage 24. It does not read arbitrary audio/video paths, modify source WAVs, evaluate answer content, or rewrite model text.

## Runtime profile

The official model is `large-v3-turbo`, pinned to model ID `mobiuslabsgmbh/faster-whisper-large-v3-turbo` and revision `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`. `auto` chooses CUDA/float16 only when CTranslate2 reports a CUDA device and float16 support; otherwise it chooses CPU/int8. It never substitutes a smaller model. A cached exact revision is loaded with `local_files_only=true` automatically.

## Command

```powershell
python scripts\transcribe_stt_session.py --session-id SES_000001
```

Optional flags are `--force-rebuild`, `--model-profile {auto,cuda-float16,cpu-int8}`, `--local-files-only`, and `--output-root`. Input audio is resolved exclusively from the ready Stage 24 manifest.

## Fixed transcription options

The service uses Korean transcription (`language=ko`, `task=transcribe`), word timestamps, no VAD filtering, no previous-answer conditioning, beam size 5, and temperature 0. Initial prompts, hotwords, translation, spelling correction, LLM correction, summarization, content evaluation, and scoring are not used.

Model seconds are multiplied by 1000 and rounded to the nearest integer millisecond with halves rounded up. Relative timestamps begin at each answer WAV's zero point. Session timestamps add the Stage 24 answer start time. A boundary rounding adjustment is limited to 1 ms and is recorded as `TIMESTAMP_ROUNDING_ADJUSTED`.

Faster-Whisper can attach word timestamps slightly outside its own segment boundary. Word timestamps are preserved; the public segment boundary is expanded to contain its words, the original rounded model boundary remains in `modelStartMsRelative` and `modelEndMsRelative`, and `SEGMENT_BOUNDARY_EXPANDED_TO_WORDS` is recorded. Neither segment nor word timestamps may leave the answer boundary.

## Output and review

Ignored runtime output is written under `data/output/stt_transcription/<sessionId>/`: four strict answer JSON documents, a session manifest, technical validation, a human review packet, and a technical report. Output contracts exclude participant IDs, source media names, and internal paths. Re-running an unchanged input/model/options combination returns `reused: true`; a forced rebuild is validated in a staging directory before atomic replacement.

Unit tests inject a fake adapter and never load or download a model. Actual transcript output and model/cache files must remain outside Git.
