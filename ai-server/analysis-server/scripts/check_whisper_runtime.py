"""Report whether the local runtime can execute faster-whisper on CUDA."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import ctranslate2


NVIDIA_SMI_TIMEOUT_SECONDS = 10


def package_version(name: str) -> str | None:
    """Return an installed package version without importing the package."""
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def classify_runtime_error(error: BaseException | str) -> str:
    """Classify representative CUDA and NVIDIA library failures."""
    message = str(error).lower()
    if any(token in message for token in ("cublas", "cublas64", "libcublas")):
        return "CUBLAS_NOT_FOUND"
    if any(token in message for token in ("cudnn", "cudnn64", "libcudnn")):
        return "CUDNN_NOT_FOUND"
    if "compute type" in message and any(
        token in message for token in ("unsupported", "not supported", "invalid")
    ):
        return "UNSUPPORTED_COMPUTE_TYPE"
    if any(
        token in message
        for token in (
            "no cuda device",
            "no cuda-capable device",
            "cuda device count is 0",
            "invalid device ordinal",
            "cuda device not found",
        )
    ):
        return "CUDA_DEVICE_NOT_FOUND"
    if any(
        token in message
        for token in (
            "cuda runtime",
            "cuda driver",
            "cudart",
            "nvcuda.dll",
            "cudaerror",
            "cuda initialization",
            "failed to initialize cuda",
        )
    ):
        return "CUDA_RUNTIME_ERROR"
    return "UNKNOWN_RUNTIME_ERROR"


def error_entry(code: str, detail: BaseException | str) -> dict[str, str]:
    return {"code": code, "detail": str(detail)}


def query_nvidia_smi() -> tuple[dict[str, Any], dict[str, str] | None]:
    """Query only the GPU fields needed for this runtime report."""
    executable = shutil.which("nvidia-smi")
    result: dict[str, Any] = {
        "executable_available": executable is not None,
        "gpu_name": None,
        "total_vram_mib": None,
        "used_vram_mib": None,
    }
    if executable is None:
        return result, error_entry("NVIDIA_SMI_NOT_FOUND", "nvidia-smi was not found on PATH")

    command = [
        executable,
        "--query-gpu=name,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=NVIDIA_SMI_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        result["executable_available"] = False
        return result, error_entry("NVIDIA_SMI_NOT_FOUND", exc)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return result, error_entry("UNKNOWN_RUNTIME_ERROR", exc)

    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"nvidia-smi exited with code {completed.returncode}"
        return result, error_entry(classify_runtime_error(detail), detail)

    first_line = next((line for line in completed.stdout.splitlines() if line.strip()), "")
    fields = [field.strip() for field in first_line.split(",")]
    if len(fields) != 3:
        return result, error_entry("UNKNOWN_RUNTIME_ERROR", "Unexpected nvidia-smi output")

    result["gpu_name"] = fields[0]
    try:
        result["total_vram_mib"] = int(fields[1])
        result["used_vram_mib"] = int(fields[2])
    except ValueError as exc:
        return result, error_entry("UNKNOWN_RUNTIME_ERROR", exc)
    return result, None


def collect_runtime_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "python_version": platform.python_version(),
        "faster_whisper_version": package_version("faster-whisper"),
        "ctranslate2_version": package_version("ctranslate2"),
        "cuda_device_count": None,
        "compute_types": {"cpu": [], "cuda": []},
        "nvidia_smi": {},
        "errors": [],
    }
    errors: list[dict[str, str]] = report["errors"]

    try:
        report["compute_types"]["cpu"] = sorted(
            ctranslate2.get_supported_compute_types("cpu")
        )
    except Exception as exc:  # CTranslate2 raises runtime-specific exception types.
        errors.append(error_entry(classify_runtime_error(exc), exc))

    try:
        device_count = ctranslate2.get_cuda_device_count()
        report["cuda_device_count"] = device_count
        if device_count < 1:
            errors.append(error_entry("CUDA_DEVICE_NOT_FOUND", "CTranslate2 reported zero CUDA devices"))
        else:
            report["compute_types"]["cuda"] = sorted(
                ctranslate2.get_supported_compute_types("cuda")
            )
    except Exception as exc:  # CTranslate2 raises runtime-specific exception types.
        errors.append(error_entry(classify_runtime_error(exc), exc))

    nvidia_result, nvidia_error = query_nvidia_smi()
    report["nvidia_smi"] = nvidia_result
    if nvidia_error is not None:
        errors.append(nvidia_error)
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = collect_runtime_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
