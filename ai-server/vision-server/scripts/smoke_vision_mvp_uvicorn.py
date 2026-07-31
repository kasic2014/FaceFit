"""Start Uvicorn, exercise the actual Stage 23 HTTP contract, then stop it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ANALYSIS_MODE = "SINGLE_SESSION_BASELINE_RELATIVE_MVP"
REQUIRED_PATHS = {
    "/health",
    "/ready",
    "/api/v1/vision/jobs",
    "/api/v1/vision/jobs/{job_id}",
    "/api/v1/vision/sessions/{session_id}/feedback",
}


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str, dict[str, Any]]:
    body = (
        json.dumps(payload, allow_nan=False).encode("utf-8")
        if payload is not None
        else None
    )
    request = Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
    value = json.loads(
        raw.decode("utf-8"),
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON value: {token}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError("HTTP JSON root must be an object")
    return status, content_type, value


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        return connection.connect_ex((host, port)) == 0


def _safe_response(value: dict[str, Any]) -> bool:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    lower = text.lower()
    forbidden = (
        "ptc_",
        "\\data\\",
        "/data/",
        "participantid",
        "participant_id",
        "videopath",
        "outputpath",
        "consentreference",
        "metadatareference",
        "raterid",
        "gazescore",
        "posturescore",
        "totalscore",
        "interviewscore",
        "passprobability",
        "confidencescore",
        '"anxiety"',
        '"concentration"',
        '"personality"',
        '"emotion"',
    )
    return not any(token in lower for token in forbidden)


def _result(
    method: str,
    path: str,
    status: int,
    content_type: str,
    *,
    expected_status: int,
    schema_valid: bool,
) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "http_status": status,
        "expected_status": expected_status,
        "content_type": content_type.split(";", 1)[0].lower(),
        "schema_valid": schema_valid,
        "passed": (
            status == expected_status
            and content_type.lower().startswith("application/json")
            and schema_valid
        ),
    }


def run_smoke(
    *,
    vision_root: Path,
    host: str,
    port: int,
    session_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if _port_open(host, port):
        raise RuntimeError("Requested validation port is already occupied")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "VISION_API_ENV": "validation",
            "VISION_API_HOST": host,
            "VISION_API_PORT": str(port),
            "VISION_API_ALLOWED_ORIGINS": "",
            "VISION_API_ENABLE_DOCS": "true",
            "VISION_API_OUTPUT_ROOT": str(
                vision_root / "data" / "output"
            ),
        }
    )
    process = subprocess.Popen(
        command,
        cwd=vision_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=(
            subprocess.CREATE_NO_WINDOW
            if os.name == "nt"
            else 0
        ),
    )
    results: list[dict[str, Any]] = []
    base_url = f"http://{host}:{port}"
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Uvicorn exited before becoming healthy")
            try:
                status, _, health = _request(base_url, "GET", "/health")
                if status == 200 and health.get("status") == "UP":
                    break
            except (OSError, URLError, ValueError):
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Uvicorn health timeout")

        status, content_type, health = _request(
            base_url, "GET", "/health"
        )
        results.append(
            _result(
                "GET",
                "/health",
                status,
                content_type,
                expected_status=200,
                schema_valid=(
                    health.get("status") == "UP"
                    and _safe_response(health)
                ),
            )
        )
        status, content_type, ready = _request(
            base_url, "GET", "/ready"
        )
        results.append(
            _result(
                "GET",
                "/ready",
                status,
                content_type,
                expected_status=200,
                schema_valid=(
                    ready.get("status") == "READY"
                    and ready.get("scoringAvailable") is False
                    and _safe_response(ready)
                ),
            )
        )
        status, content_type, openapi = _request(
            base_url, "GET", "/openapi.json"
        )
        paths = openapi.get("paths", {})
        results.append(
            _result(
                "GET",
                "/openapi.json",
                status,
                content_type,
                expected_status=200,
                schema_valid=(
                    isinstance(paths, dict)
                    and REQUIRED_PATHS.issubset(paths)
                    and _safe_response(openapi)
                ),
            )
        )
        feedback_path = (
            f"/api/v1/vision/sessions/{session_id}/feedback"
        )
        status, content_type, feedback = _request(
            base_url, "GET", feedback_path
        )
        reasons = feedback.get("scoringUnavailableReasons")
        results.append(
            _result(
                "GET",
                feedback_path,
                status,
                content_type,
                expected_status=200,
                schema_valid=(
                    feedback.get("sessionId") == session_id
                    and feedback.get("scores") is None
                    and isinstance(reasons, list)
                    and _safe_response(feedback)
                ),
            )
        )
        status, content_type, created = _request(
            base_url,
            "POST",
            "/api/v1/vision/jobs",
            {
                "sessionId": session_id,
                "analysisMode": ANALYSIS_MODE,
                "forceRebuild": False,
            },
        )
        job_id = created.get("jobId")
        results.append(
            _result(
                "POST",
                "/api/v1/vision/jobs",
                status,
                content_type,
                expected_status=201,
                schema_valid=(
                    isinstance(job_id, str)
                    and created.get("status")
                    == "SUCCEEDED_WITH_LIMITATIONS"
                    and created.get("resultAvailable") is True
                    and _safe_response(created)
                ),
            )
        )
        job_path = f"/api/v1/vision/jobs/{job_id}"
        status, content_type, loaded = _request(
            base_url, "GET", job_path
        )
        results.append(
            _result(
                "GET",
                "/api/v1/vision/jobs/{job_id}",
                status,
                content_type,
                expected_status=200,
                schema_valid=(
                    loaded.get("jobId") == job_id
                    and loaded.get("status")
                    == "SUCCEEDED_WITH_LIMITATIONS"
                    and _safe_response(loaded)
                ),
            )
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    port_left_occupied = _port_open(host, port)
    return {
        "status": (
            "PASSED"
            if results
            and all(item["passed"] for item in results)
            and not port_left_occupied
            else "FAILED"
        ),
        "uvicorn_started": bool(results),
        "uvicorn_stopped": process.poll() is not None,
        "port_left_occupied": port_left_occupied,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vision-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--session-id", default="SES_000001")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_smoke(
        vision_root=args.vision_root.resolve(),
        host=args.host,
        port=args.port,
        session_id=args.session_id,
        timeout_seconds=args.timeout_seconds,
    )
    text = (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
