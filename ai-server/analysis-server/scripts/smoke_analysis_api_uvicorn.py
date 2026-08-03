"""Launch uvicorn on port 8002, exercise real HTTP routes, and release the port."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.25)
        return client.connect_ex((host, port)) == 0


def wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("uvicorn did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if port_open(args.host, args.port):
        raise RuntimeError(f"port {args.port} is already in use")
    environment = os.environ.copy()
    environment.update({
        "ANALYSIS_API_HOST": args.host,
        "ANALYSIS_API_PORT": str(args.port),
        "ANALYSIS_API_OUTPUT_ROOT": "data/output",
        "ANALYSIS_API_ENABLE_DOCS": "true",
        "ANALYSIS_API_EXPOSE_TRANSCRIPT_TEXT": "true",
        "PYTHONPATH": str(ROOT),
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", args.host, "--port", str(args.port)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://{args.host}:{args.port}"
    report: dict = {"status": "FAIL", "port": args.port, "checks": {}}
    try:
        wait_for_server(base)
        with httpx.Client(base_url=base, timeout=30.0) as client:
            responses = {
                "health": client.get("/health"),
                "ready": client.get("/ready"),
                "openapi": client.get("/openapi.json"),
                "transcription": client.get("/api/v1/analysis/sessions/SES_000001/transcription"),
                "speechCharacteristics": client.get("/api/v1/analysis/sessions/SES_000001/speech-characteristics"),
            }
            created = client.post("/api/v1/analysis/jobs", json={
                "sessionId": "SES_000001", "pipeline": "SPEECH_CHARACTERISTICS", "forceRebuild": False,
            })
            responses["jobCreate"] = created
            responses["jobRead"] = client.get(f"/api/v1/analysis/jobs/{created.json()['jobId']}")
        checks = {name: response.status_code for name, response in responses.items()}
        job = responses["jobCreate"].json()
        speech = responses["speechCharacteristics"].json()
        checks.update({
            "jobSucceededWithWarnings": job.get("status") == "SUCCEEDED_WITH_WARNINGS",
            "jobWarningsPresent": bool(job.get("warnings")),
            "speechHasFourAnswers": len(speech.get("answers", [])) == 4,
            "requestIdPresent": all("X-Request-ID" in response.headers for response in responses.values()),
        })
        report = {
            "status": "PASS" if (
                all(value in {200, 201} for value in list(checks.values())[:7])
                and all(checks[key] is True for key in (
                    "jobSucceededWithWarnings", "jobWarningsPresent", "speechHasFourAnswers", "requestIdPresent"
                ))
            ) else "FAIL",
            "port": args.port,
            "checks": checks,
            "jobId": job.get("jobId"),
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        deadline = time.monotonic() + 10
        while port_open(args.host, args.port) and time.monotonic() < deadline:
            time.sleep(0.2)
        report["processExitCode"] = process.returncode
        report["portReleased"] = not port_open(args.host, args.port)
        if not report["portReleased"]:
            report["status"] = "FAIL"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
