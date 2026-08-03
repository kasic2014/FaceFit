# Face-Fit Analysis API (Stage 27)

The Analysis API exposes existing Stage 25 Korean STT and Stage 26 measurement-only speech characteristics through FastAPI. It does not run Stage 24 automatically, accept participant identifiers or file paths, score an interview, or invoke pipeline CLIs. Stage 27.1 executes analysis through a bounded in-process worker queue rather than inside the HTTP request thread.

## Runtime

Install the API and test dependencies in the Analysis virtual environment:

```powershell
python -m pip install -r requirements-api.txt -r requirements-test.txt
python -m pip check
```

Start the server from `ai-server/analysis-server`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Configuration uses the `ANALYSIS_API_` prefix. Defaults are `ENV=development`, `HOST=127.0.0.1`, `PORT=8002`, no CORS origins, `OUTPUT_ROOT=data/output`, and `LOG_LEVEL=INFO`. Development enables docs and transcript text. Production disables both unless explicitly enabled. Boolean values accept only `true` or `false`; wildcard CORS is rejected.

Async runtime defaults are one worker, queue capacity 16, execution-lock wait 300 seconds, stale-lock threshold 900 seconds, and graceful-shutdown wait 30 seconds. These use `ANALYSIS_API_JOB_MAX_WORKERS`, `ANALYSIS_API_JOB_QUEUE_CAPACITY`, `ANALYSIS_API_JOB_LOCK_WAIT_SECONDS`, `ANALYSIS_API_STALE_LOCK_SECONDS`, and `ANALYSIS_API_SHUTDOWN_WAIT_SECONDS`. STT GPU execution remains process-serialized even if more workers are configured; readiness reports a GPU contention warning when the worker count exceeds one.

## Routes

- `GET /health` checks process liveness without model loading.
- `GET /ready` checks output/job storage, imports, and Stage 24~26 resolvers without model loading.
- `POST /api/v1/analysis/jobs` accepts `sessionId`, `pipeline`, and `forceRebuild`.
- `GET /api/v1/analysis/jobs/{job_id}` reads an atomic, restart-safe job record.
- `GET /api/v1/analysis/sessions/{session_id}/transcription` returns sanitized Stage 25 output.
- `GET /api/v1/analysis/sessions/{session_id}/speech-characteristics` returns sanitized Stage 26 measurements.
- `GET /openapi.json` returns the public contract even when interactive docs are disabled.

Pipelines are `STT_TRANSCRIPTION`, `SPEECH_CHARACTERISTICS`, and `STT_AND_SPEECH`. POST atomically persists `QUEUED`, enqueues the job, and returns immediately. Workers perform `QUEUED -> RUNNING -> terminal` transitions with UTC timestamps and queue/execution/total durations. A successful or in-progress non-force job is reused; `forceRebuild=true` always creates a new job but cannot execute concurrently with the same session/pipeline key.

Execution locks are strict JSON files below ignored `data/output/analysis_api/locks`. They are acquired with exclusive file creation and always released after success or failure. A stale lock is recovered only when it exceeds the configured age, its owner is missing or terminal, and the owner is not active in this process. Corrupted locks are preserved and reported instead of being deleted.

At startup, persisted `QUEUED` and `RUNNING` jobs are conservatively marked `FAILED` with `JOB_INTERRUPTED_BY_RESTART`; work is never silently resumed or promoted from existing result files. During shutdown, new jobs are rejected, queued/running jobs receive bounded grace time, and unfinished records are marked `JOB_INTERRUPTED_BY_SHUTDOWN` without killing Python threads.

## Job retention

Retention is disabled by default. Settings are `ANALYSIS_API_JOB_RETENTION_ENABLED=false`, `ANALYSIS_API_JOB_RETENTION_DAYS=30`, and `ANALYSIS_API_JOB_MAX_RECORDS=1000`. Cleanup targets only expired terminal job JSON. Queued/running jobs, lock owners, and records newer than the retention cutoff are protected. Stage 24~26 artifacts are never cleanup targets.

```powershell
python scripts/cleanup_analysis_jobs.py --dry-run
python scripts/cleanup_analysis_jobs.py --apply
```

Omitting both flags is a dry run.

## Privacy and interpretation

When transcript exposure is disabled, answer, segment, and word text are all `null`; timestamps, counts, language, and warnings remain available. Responses exclude participant data, filesystem paths, cache paths, source video information, consent/metadata/rater data, and stack traces.

Speech responses contain technical measurements only. They never contain scores, grades, confidence, anxiety, personality, emotion, pass probability, speed/loudness judgments, or monotone judgments. Filler matches require human review, and pitch is a physical F0 measurement only.

Every response includes `X-Request-ID`. Errors use `{code, message, requestId, details}`. Configured CORS permits only explicit HTTP(S) origins, `GET`/`POST`, and `Content-Type`/`X-Request-ID` headers.

## Validation

```powershell
python -m unittest discover -s tests -p "test_*.py"
python runtime_tests/test_analysis_api_runtime_stage27.py
python runtime_tests/test_analysis_api_async_runtime_stage271.py
python scripts/validate_analysis_api.py
python scripts/smoke_analysis_api_uvicorn.py --report data/output/analysis_api_validation/uvicorn_smoke_1.json
python scripts/smoke_analysis_api_uvicorn.py --report data/output/analysis_api_validation/uvicorn_smoke_2.json
```

Validation evidence and job records are written below ignored `data/output/analysis_api_validation` and `data/output/analysis_api/jobs` directories.
