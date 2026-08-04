# Face-Fit Vision and Analysis integration contract

Stage 28 defines the Backend handoff contract that combines existing Vision and Analysis results. The integration package calls only public HTTP endpoints. Neither AI server imports or calls the other server.

## Identifiers and requests

- Session IDs match `^SES_\d{6}$`.
- Answer IDs match `^ANS_\d{6}$`.
- Job IDs are opaque values returned by each service.
- Vision Job creation: `POST /api/v1/vision/jobs` with `analysisMode=SINGLE_SESSION_BASELINE_RELATIVE_MVP` and `forceRebuild=false`.
- Analysis Job creation: `POST /api/v1/analysis/jobs` with `pipeline=STT_AND_SPEECH` and `forceRebuild=false`.
- Optional media paths, participant IDs, transcripts, consent objects, or model paths are never accepted by the integration CLI.

## Polling sequence

1. Check `/health` and `/ready` on both services.
2. Create or reuse the Vision and Analysis Jobs independently.
3. Poll `GET /api/v1/vision/jobs/{jobId}` and `GET /api/v1/analysis/jobs/{jobId}` independently.
4. Stop immediately at a terminal status: `SUCCEEDED`, `SUCCEEDED_WITH_WARNINGS`, `SUCCEEDED_WITH_LIMITATIONS`, or `FAILED`.
5. Fetch Vision feedback, transcription, and speech characteristics only when their Job succeeded.
6. Validate Session IDs, Answer sets, intervals, and event timestamps before building the integrated result.

The default polling interval is 250 ms and the maximum wait is 120 seconds. HTTP retries are finite. Timeout is reported as `INTEGRATION_TIMEOUT`. One component failure does not discard another component's usable result.

## Result endpoints consumed

- `GET /api/v1/vision/sessions/{sessionId}/feedback`
- `GET /api/v1/analysis/sessions/{sessionId}/transcription`
- `GET /api/v1/analysis/sessions/{sessionId}/speech-characteristics`

## Status mapping

The common component statuses are `READY`, `READY_WITH_WARNINGS`, `NOT_READY`, `FAILED`, and `UNAVAILABLE`. The original status is retained in `sourceStatus`.

- Vision `SUCCEEDED` maps to `READY`.
- Vision `SUCCEEDED_WITH_LIMITATIONS` maps to `READY_WITH_WARNINGS`.
- Analysis `SUCCEEDED` maps to `READY`.
- Analysis `SUCCEEDED_WITH_WARNINGS` maps to `READY_WITH_WARNINGS`.
- A source `FAILED` status maps to `FAILED`.

Final statuses are:

- `INTEGRATED_READY`: all components are ready without warnings or limitations.
- `INTEGRATED_READY_WITH_WARNINGS`: all results are usable and a warning or limitation exists.
- `INTEGRATED_PARTIAL`: at least one result is usable and at least one component is unavailable, not ready, or failed.
- `INTEGRATED_FAILED`: mandatory Session, Answer, interval, timestamp, or response validation failed, or no component is usable.

`SES_000001` is expected to be `INTEGRATED_READY_WITH_WARNINGS` because Head Pose and existing STT/speech warnings are retained.

## Warning and error shapes

Warnings contain `source`, `code`, `message`, nullable `answerId`, and `reviewRequired`. Sources are `VISION`, `TRANSCRIPTION`, `SPEECH`, and `INTEGRATION`. Warnings are deduplicated by `source + code + answerId`; identical codes from different sources remain distinct.

Errors contain `source`, `code`, `message`, and `retryable`. Internal exception text and stack traces are never persisted. Integration error codes include:

- `SESSION_ID_MISMATCH`
- `ANSWER_SET_MISMATCH`
- `ANSWER_INTERVAL_MISMATCH`
- `TIMESTAMP_OUT_OF_RANGE`
- `COMPONENT_RESULT_NOT_READY`
- `COMPONENT_JOB_FAILED`
- `COMPONENT_HTTP_ERROR`
- `COMPONENT_RESPONSE_INVALID`
- `INTEGRATION_TIMEOUT`

## Answer and timestamp rules

The approved `SES_000001` Answer set is `ANS_000001` through `ANS_000004`. Vision, transcription, and speech Answer sets must match exactly. Missing, extra, duplicate, or reordered-by-repair data is not accepted.

Approved intervals use `[start, end)`:

- `ANS_000001`: `[11000, 50000)`
- `ANS_000002`: `[51000, 107000)`
- `ANS_000003`: `[108000, 160000)`
- `ANS_000004`: `[161000, 192000)`

Segment, word, and filler intervals satisfy `answerStartMs <= eventStartMs < eventEndMs <= answerEndMs`. A maximum 1 ms tolerance is used only when the upstream transcription contract explicitly reports `timestampToleranceMs=1`. Timestamps are never silently clamped.

## Privacy and scoring

The default is `FACEFIT_INTEGRATION_EXPOSE_TRANSCRIPT_TEXT=false`. In that mode, full transcript text, segment text, and word text are excluded while counts and timestamps remain usable. Transcript text may be included only with explicit configuration. Production systems should keep the default.

Integrated JSON excludes participant IDs, consent, rater IDs, absolute paths, source filenames, model-cache paths, raw media, and evaluation fields. Strict JSON rejects `NaN` and Infinity. All JSON writes are atomic.

`scoringAvailable` is always false and the reasons are `SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP` and `THRESHOLD_EVIDENCE_NOT_APPROVED`. The contract does not create overall, gaze, posture, voice, STT-accuracy, interview, grade, confidence, or pass-probability scores.

The known limitation `ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED` is retained. Stage 28 reuses existing results and does not claim that the Stage 27.2 GPU dependency issue is resolved.

## Configuration and CLI

Environment variables:

- `FACEFIT_VISION_API_BASE_URL` (default `http://127.0.0.1:8000`)
- `FACEFIT_ANALYSIS_API_BASE_URL` (default `http://127.0.0.1:8002`)
- `FACEFIT_INTEGRATION_POLL_INTERVAL_MS` (default `250`)
- `FACEFIT_INTEGRATION_TIMEOUT_SECONDS` (default `120`)
- `FACEFIT_INTEGRATION_EXPOSE_TRANSCRIPT_TEXT` (default `false`)

Host execution:

```powershell
& $analysisPython ai-server/integration/scripts/run_integrated_session.py `
  --session-id SES_000001 `
  --vision-base-url http://127.0.0.1:8000 `
  --analysis-base-url http://127.0.0.1:8002
```

Docker DNS uses `http://vision-server:8000` and `http://analysis-server:8002`. Output is written below ignored `ai-server/integration/data/output/<sessionId>/` as `integrated_session.json`, `integration_validation.json`, `component_status.json`, and `integration_report.md`.

This package is the specification for a future Spring Boot client and DTO layer. It does not add or modify Spring Boot code.
