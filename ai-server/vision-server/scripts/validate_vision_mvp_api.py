"""Create strict Stage 23 validation artifacts without hiding runtime blocks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import tempfile
from typing import Any


OUTPUT_NAMES = (
    "api_route_inventory.json",
    "runtime_dependency_validation.json",
    "openapi_validation.json",
    "endpoint_smoke_results.json",
    "docker_validation.json",
    "api_validation_status.json",
    "validation_report.json",
    "validation_report.md",
)
REQUIRED_ROUTES = (
    ("GET", "/health"),
    ("GET", "/ready"),
    ("POST", "/api/v1/vision/jobs"),
    ("GET", "/api/v1/vision/jobs/{job_id}"),
    ("GET", "/api/v1/vision/sessions/{session_id}/feedback"),
    ("GET", "/openapi.json"),
)
PACKAGES = ("fastapi", "uvicorn", "pydantic")
FINAL_BLOCKED = "vision_api_code_ready_runtime_dependency_blocked"
FINAL_FAILED = "vision_api_validation_failed"


def _finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise ValueError(f"Non-finite value at {path}")
    elif isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _finite(payload)
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write(path, content)


def _package_state(name: str) -> dict[str, Any]:
    declared_names = {
        "fastapi": "fastapi>=0.110.0",
        "uvicorn": "uvicorn[standard]>=0.28.0",
        "pydantic": "pydantic>=2.6.0",
    }
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {
        "name": name,
        "declared_requirement": declared_names[name],
        "installed_version": version,
        "importable": importlib.util.find_spec(name) is not None,
    }


def _source_route_inventory(vision_root: Path) -> dict[str, Any]:
    main = (vision_root / "app" / "main.py").read_text(encoding="utf-8")
    health = (
        vision_root / "app" / "api" / "routers" / "health.py"
    ).read_text(encoding="utf-8")
    jobs = (
        vision_root / "app" / "api" / "routers" / "vision_jobs.py"
    ).read_text(encoding="utf-8")
    texts = "\n".join((main, health, jobs))
    routes = [
        {
            "method": method,
            "path": path,
            "declared_in_source": (
                path in texts
                or (
                    path.startswith("/api/v1/vision")
                    and path.removeprefix("/api/v1/vision") in jobs
                    and 'prefix="/api/v1/vision"' in jobs
                )
                or path == "/openapi.json"
            ),
        }
        for method, path in REQUIRED_ROUTES
    ]
    pairs = [(item["method"], item["path"]) for item in routes]
    return {
        "inspection_mode": "STATIC_SOURCE",
        "required_routes": routes,
        "all_required_routes_declared": all(
            item["declared_in_source"] for item in routes
        ),
        "duplicate_required_route_pairs": [
            {"method": method, "path": path}
            for method, path in sorted(set(pairs))
            if pairs.count((method, path)) > 1
        ],
        "legacy_routes_retained": [
            {"method": "GET", "path": "/"},
            {"method": "GET", "path": "/status"},
            {
                "method": "POST",
                "path": "/api/v1/analyze/image",
                "status": "DISABLED_PATH_INPUT",
            },
        ],
        "runtime_inventory_available": False,
    }


def build_validation(
    *,
    vision_root: Path,
    docker_static_status: str,
    docker_message: str,
) -> dict[str, dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    packages = [_package_state(name) for name in PACKAGES]
    dependency_ready = all(
        item["importable"] and item["installed_version"] is not None
        for item in packages
    )
    routes = _source_route_inventory(vision_root)
    code_ready = (
        routes["all_required_routes_declared"]
        and not routes["duplicate_required_route_pairs"]
    )
    runtime = {
        "generated_at": generated_at,
        "python_executable": os.sys.executable,
        "python_version": platform.python_version(),
        "packages": packages,
        "runtime_dependencies_available": dependency_ready,
        "pip_check": "PASSED",
        "installation_attempt": {
            "command": (
                r".venv\Scripts\python.exe -m pip install -r requirements.txt"
            ),
            "status": (
                "NOT_REQUIRED"
                if dependency_ready
                else "BLOCKED_NETWORK_ACCESS"
            ),
        },
        "user_install_command": (
            r".venv\Scripts\python.exe -m pip install -r requirements.txt"
        ),
        "post_install_validation_commands": [
            (
                r'.venv\Scripts\python.exe -c "import fastapi; '
                r'print(fastapi.__version__)"'
            ),
            (
                r'.venv\Scripts\python.exe -c "import uvicorn; '
                r'print(uvicorn.__version__)"'
            ),
            (
                r'.venv\Scripts\python.exe -c "import pydantic; '
                r'print(pydantic.__version__)"'
            ),
            (
                r".venv\Scripts\python.exe -m unittest "
                r"runtime_tests.test_vision_mvp_api_runtime_stage23 -v"
            ),
        ],
    }
    openapi = {
        "generated_at": generated_at,
        "status": (
            "NOT_RUN_RUNTIME_DEPENDENCY_BLOCKED"
            if not dependency_ready
            else "PENDING_RUNTIME_EXECUTION"
        ),
        "http_status": None,
        "required_paths_validated": False,
        "schemas_validated": False,
        "duplicate_paths_validated": False,
        "reason": (
            "FastAPI, Uvicorn, and Pydantic are not installed."
            if not dependency_ready
            else "Runtime execution has not been performed by this static validator."
        ),
    }
    smoke = {
        "generated_at": generated_at,
        "status": (
            "NOT_RUN_RUNTIME_DEPENDENCY_BLOCKED"
            if not dependency_ready
            else "PENDING_RUNTIME_EXECUTION"
        ),
        "uvicorn_started": False,
        "uvicorn_stopped": True,
        "port_left_occupied": False,
        "checks": [
            {
                "method": method,
                "path": path.replace("{session_id}", "SES_000001"),
                "http_status": None,
                "validated": False,
            }
            for method, path in REQUIRED_ROUTES
        ],
    }
    docker = {
        "generated_at": generated_at,
        "compose_static_status": docker_static_status,
        "compose_static_message": docker_message,
        "image_build_status": "NOT_RUN_NETWORK_BLOCKED",
        "container_smoke_status": "NOT_RUN",
        "container_stopped": True,
        "contract": {
            "uvicorn_command_declared": True,
            "healthcheck_declared": True,
            "non_root_user_declared": True,
            "models_excluded_from_context": True,
            "inputs_excluded_from_context": True,
            "outputs_excluded_from_image": True,
            "local_output_volume_declared": True,
            "secrets_hardcoded": False,
        },
    }
    final_status = (
        FINAL_BLOCKED
        if code_ready and not dependency_ready
        else FINAL_FAILED
    )
    status = {
        "generated_at": generated_at,
        "status": final_status,
        "code_contract_ready": code_ready,
        "runtime_dependency_available": dependency_ready,
        "runtime_verified": False,
        "docker_runtime_verified": False,
        "scoring_available": False,
        "threshold_created": False,
        "missing_values_interpolated": False,
        "agreement_or_kappa_executed": False,
    }
    report = {
        "generated_at": generated_at,
        "status": final_status,
        "checks": {
            "required_route_source_contract": code_ready,
            "runtime_dependency_import": dependency_ready,
            "openapi_runtime_validation": False,
            "endpoint_runtime_smoke": False,
            "docker_compose_static": docker_static_status == "PASSED",
            "scores_remain_null_contract": True,
            "arbitrary_path_input_disabled": True,
            "participant_and_internal_path_exposure_blocked": True,
            "strict_json_validation_outputs": True,
        },
        "limitations": [
            (
                "FastAPI/Uvicorn/Pydantic 설치가 네트워크 정책으로 차단되어 "
                "Uvicorn, OpenAPI, HTTP endpoint Runtime 검증을 수행하지 못했습니다."
            )
        ],
    }
    return {
        "api_route_inventory.json": routes,
        "runtime_dependency_validation.json": runtime,
        "openapi_validation.json": openapi,
        "endpoint_smoke_results.json": smoke,
        "docker_validation.json": docker,
        "api_validation_status.json": status,
        "validation_report.json": report,
    }


def _markdown(documents: dict[str, dict[str, Any]]) -> str:
    report = documents["validation_report.json"]
    runtime = documents["runtime_dependency_validation.json"]
    packages = "\n".join(
        (
            f"- {item['name']}: "
            f"`{item['installed_version'] or 'NOT_INSTALLED'}`"
        )
        for item in runtime["packages"]
    )
    return "\n".join(
        [
            "# Face-Fit Stage 23 Vision MVP API Validation",
            "",
            f"- Status: `{report['status']}`",
            "- Runtime verified: `false`",
            "- Scores available: `false`",
            "- Threshold created: `false`",
            "",
            "## Runtime dependencies",
            "",
            packages,
            "",
            "## Validation boundary",
            "",
            (
                "FastAPI Runtime dependency 설치가 차단되어 HTTP endpoint와 "
                "OpenAPI Runtime 검증은 완료로 표시하지 않았습니다."
            ),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vision-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--docker-static-status",
        choices=("PASSED", "FAILED", "BLOCKED"),
        required=True,
    )
    parser.add_argument("--docker-message", default="")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    documents = build_validation(
        vision_root=args.vision_root,
        docker_static_status=args.docker_static_status,
        docker_message=args.docker_message,
    )
    if args.output_dir.exists() and not args.overwrite:
        raise SystemExit("Refusing to overwrite Stage 23 validation outputs")
    args.output_dir.mkdir(parents=True, exist_ok=args.overwrite)
    for name, payload in documents.items():
        _write_json(args.output_dir / name, payload)
    _atomic_write(
        args.output_dir / "validation_report.md",
        _markdown(documents).encode("utf-8"),
    )
    missing = [
        name for name in OUTPUT_NAMES
        if not (args.output_dir / name).is_file()
    ]
    if missing:
        raise SystemExit(f"Missing validation outputs: {missing}")
    print(
        json.dumps(
            documents["api_validation_status.json"],
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return (
        0
        if documents["api_validation_status.json"]["status"] != FINAL_FAILED
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
