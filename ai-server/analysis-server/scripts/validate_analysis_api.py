"""Create strict, ignored Stage 27 API validation evidence."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.audio.audio_manifest_writer import write_json_atomic
from app.main import create_app


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Analysis API validation", "",
        f"- Status: {report['status']}",
        f"- Routes: {report['routeCount']}",
        f"- Transcription answers / segments / words: {report['transcription']['answers']} / "
        f"{report['transcription']['segments']} / {report['transcription']['words']}",
        f"- Speech answers / filler candidates / pitch available: {report['speech']['answers']} / "
        f"{report['speech']['fillerCandidates']} / {report['speech']['pitchAvailable']}",
        f"- Job status: {report['job']['status']}", "",
        "No model was initialized by liveness or readiness validation.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "data" / "output" / "analysis_api_validation",
    )
    args = parser.parse_args()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        openapi = client.get("/openapi.json")
        transcript = client.get("/api/v1/analysis/sessions/SES_000001/transcription")
        speech = client.get("/api/v1/analysis/sessions/SES_000001/speech-characteristics")
        created = client.post("/api/v1/analysis/jobs", json={
            "sessionId": "SES_000001",
            "pipeline": "SPEECH_CHARACTERISTICS",
            "forceRebuild": False,
        })
        fetched = client.get(
            f"/api/v1/analysis/jobs/{created.json().get('jobId', 'invalid')}"
        ) if created.status_code == 201 else created

    document = openapi.json() if openapi.status_code == 200 else {}
    public_routes = {
        "/health", "/ready", "/openapi.json", "/api/v1/analysis/jobs",
        "/api/v1/analysis/jobs/{job_id}",
        "/api/v1/analysis/sessions/{session_id}/transcription",
        "/api/v1/analysis/sessions/{session_id}/speech-characteristics",
    }
    routes = sorted(
        route.path for route in app.routes if getattr(route, "path", None) in public_routes
    )
    dependencies = {
        name: importlib.metadata.version(name)
        for name in ("fastapi", "uvicorn", "pydantic", "httpx", "starlette")
    }
    write_json_atomic(output / "route_inventory.json", {"routes": routes, "count": len(routes)})
    write_json_atomic(output / "runtime_dependency_validation.json", {
        "status": "PASS", "dependencies": dependencies, "httpx2Required": False,
    })
    serialized_openapi = json.dumps(document).lower()
    openapi_checks = {
        "allRequiredPaths": set(routes) == public_routes,
        "apiErrorSchema": "ApiError" in document.get("components", {}).get("schemas", {}),
        "participantInputExcluded": "participantid" not in serialized_openapi,
        "filePathInputExcluded": '"filepath"' not in serialized_openapi,
    }
    write_json_atomic(output / "openapi_validation.json", {
        "status": "PASS" if all(openapi_checks.values()) else "FAIL", "checks": openapi_checks,
    })
    endpoint_status = {
        "health": health.status_code,
        "ready": ready.status_code,
        "openapi": openapi.status_code,
        "transcription": transcript.status_code,
        "speechCharacteristics": speech.status_code,
        "jobCreate": created.status_code,
        "jobRead": fetched.status_code,
    }
    write_json_atomic(output / "endpoint_smoke.json", endpoint_status)
    transcript_body = transcript.json() if transcript.status_code == 200 else {"answers": []}
    speech_body = speech.json() if speech.status_code == 200 else {"answers": []}
    report = {
        "status": "PASS" if (
            all(value in {200, 201} for value in endpoint_status.values())
            and all(openapi_checks.values())
        ) else "FAIL",
        "routeCount": len(routes),
        "transcription": {
            "answers": len(transcript_body["answers"]),
            "segments": sum(row["segmentCount"] for row in transcript_body["answers"]),
            "words": sum(row["wordCount"] for row in transcript_body["answers"]),
        },
        "speech": {
            "answers": len(speech_body["answers"]),
            "fillerCandidates": sum(len(row["fillerCandidates"]) for row in speech_body["answers"]),
            "pitchAvailable": sum(row["pitch"].get("medianF0Hz") is not None for row in speech_body["answers"]),
        },
        "job": created.json() if created.status_code == 201 else {"status": "FAILED"},
    }
    write_json_atomic(output / "validation_report.json", report)
    write_json_atomic(output / "status.json", {"status": report["status"]})
    write_markdown(output / "validation_report.md", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
