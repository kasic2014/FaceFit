"""Exercise an already-running Analysis API container over real HTTP."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}
PROTECTED_TOKENS = (
    "participantid",
    "filepath",
    "stacktrace",
    "traceback",
    "/models/faster-whisper",
    "c:\\users\\",
    "/users/",
    "/home/",
)


class ContainerSmokeError(RuntimeError):
    pass


def _reject_constant(value: str) -> None:
    raise ContainerSmokeError(f"non-finite JSON constant: {value}")


def _strict_json(raw: bytes) -> Any:
    try:
        decoded = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        json.dumps(decoded, ensure_ascii=False, allow_nan=False)
        return decoded
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContainerSmokeError(f"invalid strict JSON response: {exc}") from exc


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), _strict_json(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        detail = _strict_json(body) if body else {"error": "empty response"}
        raise ContainerSmokeError(f"{method} {path} returned {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", type(exc).__name__)
        raise ContainerSmokeError(f"{method} {path} failed: {reason}") from exc


def _wait_for_health(base_url: str, timeout_seconds: float, poll_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        try:
            status, payload = _request(base_url, "GET", "/health", timeout=3)
            if status == 200 and payload.get("status") == "UP":
                return attempts
        except ContainerSmokeError:
            pass
        time.sleep(poll_seconds)
    raise ContainerSmokeError("container health wait exceeded the bounded timeout")


def _assert_safe(payloads: list[Any]) -> None:
    serialized = json.dumps(payloads, ensure_ascii=False, allow_nan=False).lower()
    found = [token for token in PROTECTED_TOKENS if token in serialized]
    if found:
        raise ContainerSmokeError(f"protected response token exposed: {found}")


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run(args: argparse.Namespace) -> dict[str, Any]:
    health_attempts = _wait_for_health(args.base_url, args.timeout_seconds, args.poll_seconds)
    health_status, health = _request(args.base_url, "GET", "/health")
    ready_status, ready = _request(args.base_url, "GET", "/ready")
    openapi_status, openapi = _request(args.base_url, "GET", "/openapi.json")
    job_status, job = _request(args.base_url, "POST", "/api/v1/analysis/jobs", {
        "sessionId": args.session_id,
        "pipeline": "STT_AND_SPEECH",
        "forceRebuild": False,
    })
    initial_status = job.get("status")
    deadline = time.monotonic() + args.timeout_seconds
    poll_count = 0
    while job.get("status") not in TERMINAL:
        if time.monotonic() >= deadline:
            raise ContainerSmokeError("job polling exceeded the bounded timeout")
        time.sleep(args.poll_seconds)
        poll_count += 1
        _, job = _request(args.base_url, "GET", f"/api/v1/analysis/jobs/{job['jobId']}")
    transcription_status, transcription = _request(
        args.base_url, "GET", f"/api/v1/analysis/sessions/{args.session_id}/transcription"
    )
    speech_status, speech = _request(
        args.base_url, "GET",
        f"/api/v1/analysis/sessions/{args.session_id}/speech-characteristics",
    )
    payloads = [health, ready, openapi, job, transcription, speech]
    _assert_safe(payloads)

    answers = transcription.get("answers", [])
    speech_answers = speech.get("answers", [])
    segments = sum(int(answer.get("segmentCount", 0)) for answer in answers)
    words = sum(int(answer.get("wordCount", 0)) for answer in answers)
    fillers = sum(len(answer.get("fillerCandidates", [])) for answer in speech_answers)
    pitch_available = sum(
        answer.get("pitch", {}).get("medianF0Hz") is not None for answer in speech_answers
    )
    checks = {
        "health200": health_status == 200,
        "ready200": ready_status == 200,
        "openapi200": openapi_status == 200,
        "jobCreate201": job_status == 201,
        "initialStatusAllowed": initial_status in {
            "QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"
        },
        "terminalWithWarnings": job.get("status") == "SUCCEEDED_WITH_WARNINGS",
        "warningsPresent": bool(job.get("warnings")),
        "transcription200": transcription_status == 200,
        "speech200": speech_status == 200,
        "answerCount": len(answers) == 4,
        "segmentCount": segments == 27,
        "wordCount": words == 307,
        "speechAnswerCount": len(speech_answers) == 4,
        "fillerCandidateCount": fillers == 1,
        "pitchAvailableCount": pitch_available == 4,
        "scoringUnavailable": ready.get("scoringAvailable") is False,
        "strictFiniteJson": all(
            not isinstance(value, float) or math.isfinite(value)
            for payload in payloads
            for value in _walk_values(payload)
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "sessionId": args.session_id,
        "healthAttempts": health_attempts,
        "pollCount": poll_count,
        "initialJobStatus": initial_status,
        "finalJobStatus": job.get("status"),
        "warningCodes": [warning.get("code") for warning in job.get("warnings", [])],
        "counts": {
            "answers": len(answers), "segments": segments, "words": words,
            "speechAnswers": len(speech_answers), "fillerCandidates": fillers,
            "pitchAvailable": pitch_available,
        },
        "checks": checks,
    }


def _walk_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--session-id", default="SES_000001")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "data" / "output" / "analysis_docker_validation"
        / "endpoint_smoke_results.json",
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or not 0 < args.poll_seconds <= 5:
        parser.error("timeouts must be positive and polling must not exceed 5 seconds")
    try:
        report = run(args)
    except ContainerSmokeError as exc:
        report = {"status": "FAIL", "errorCode": "CONTAINER_SMOKE_FAILED", "message": str(exc)}
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
