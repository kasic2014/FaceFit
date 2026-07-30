"""Validate the isolated MediaPipe vision-server environment.

This check deliberately does not download or load any MediaPipe model.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.core import config  # noqa: E402


REPORT_PATH = VISION_SERVER_ROOT / "environment_report.json"
EXPECTED_VENV_ROOT = VISION_SERVER_ROOT / ".venv"
MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "face-fit-matplotlib"
MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MATPLOTLIB_CACHE))


def _same_path(left: str | Path, right: str | Path) -> bool:
    left_normalized = os.path.normcase(str(Path(left).resolve(strict=False)))
    right_normalized = os.path.normcase(str(Path(right).resolve(strict=False)))
    return left_normalized == right_normalized


def is_python_312(version_info: Any = None) -> bool:
    """Return whether the supplied/current interpreter is Python 3.12."""

    value = sys.version_info if version_info is None else version_info
    return (value.major, value.minor) == (3, 12)


def is_expected_virtual_environment(
    *,
    prefix: str | Path | None = None,
    base_prefix: str | Path | None = None,
    executable: str | Path | None = None,
) -> bool:
    """Return whether execution is inside vision-server/.venv."""

    current_prefix = sys.prefix if prefix is None else prefix
    current_base_prefix = sys.base_prefix if base_prefix is None else base_prefix
    current_executable = sys.executable if executable is None else executable
    if _same_path(current_prefix, current_base_prefix):
        return False
    expected_executable = EXPECTED_VENV_ROOT / "Scripts" / "python.exe"
    return _same_path(current_prefix, EXPECTED_VENV_ROOT) and _same_path(
        current_executable,
        expected_executable,
    )


def inspect_mediapipe_api(
    mp_module: Any,
    tasks_python_module: Any,
    vision_module: Any,
) -> dict[str, bool]:
    """Inspect the required Tasks symbols without creating a model."""

    return {
        "tasks": hasattr(mp_module, "tasks"),
        "BaseOptions": hasattr(tasks_python_module, "BaseOptions"),
        "FaceLandmarker": hasattr(vision_module, "FaceLandmarker"),
        "FaceLandmarkerOptions": hasattr(vision_module, "FaceLandmarkerOptions"),
        "PoseLandmarker": hasattr(vision_module, "PoseLandmarker"),
        "PoseLandmarkerOptions": hasattr(vision_module, "PoseLandmarkerOptions"),
        "RunningMode": hasattr(vision_module, "RunningMode"),
        "Image": hasattr(mp_module, "Image"),
    }


def check_directory(path: Path) -> dict[str, Any]:
    """Check that a directory can be read, written, and cleaned up."""

    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_directory": path.is_dir(),
        "readable": False,
        "writable": False,
        "deletable": False,
    }
    if not result["is_directory"]:
        return result

    try:
        next(path.iterdir(), None)
        result["readable"] = True
    except OSError as exc:
        result["error"] = str(exc)
        return result

    probe = path / f".vision-environment-probe-{uuid.uuid4().hex}.tmp"
    try:
        probe.write_text("probe", encoding="utf-8")
        result["writable"] = True
        probe.unlink()
        result["deletable"] = not probe.exists()
    except OSError as exc:
        result["error"] = str(exc)
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return result


def run_pip_check() -> dict[str, Any]:
    """Run pip's installed dependency consistency check."""

    completed = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return {
        "command": [sys.executable, "-m", "pip", "check"],
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "output": output,
    }


def _package_version(distribution_name: str) -> str | None:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _opencv_distribution() -> tuple[str | None, str | None]:
    candidates = (
        "opencv-python",
        "opencv-contrib-python",
        "opencv-python-headless",
        "opencv-contrib-python-headless",
    )
    installed = [
        (name, version)
        for name in candidates
        if (version := _package_version(name)) is not None
    ]
    if len(installed) == 1:
        return installed[0]
    if not installed:
        return None, None
    return "multiple", ", ".join(f"{name}=={version}" for name, version in installed)


def collect_environment_report(
    pip_check_runner: Callable[[], dict[str, Any]] = run_pip_check,
) -> dict[str, Any]:
    """Collect all required checks and derive ready/failed status."""

    errors: list[str] = []
    warnings: list[str] = []

    python_312 = is_python_312()
    virtual_environment_active = not _same_path(sys.prefix, sys.base_prefix)
    expected_environment = is_expected_virtual_environment()
    if not python_312:
        errors.append("Python 3.12 is required.")
    if not virtual_environment_active:
        errors.append("A Python virtual environment is not active.")
    if not expected_environment:
        errors.append("The script is not running from vision-server/.venv.")

    packages: dict[str, Any] = {}
    mediapipe_api = {
        "tasks": False,
        "BaseOptions": False,
        "FaceLandmarker": False,
        "FaceLandmarkerOptions": False,
        "PoseLandmarker": False,
        "PoseLandmarkerOptions": False,
        "RunningMode": False,
        "Image": False,
    }

    mp_module = None
    try:
        # Keep third-party cache files out of the user's profile.
        import mediapipe as mp

        mp_module = mp
        packages["mediapipe"] = {
            "imported": True,
            "version": str(mp.__version__),
        }
    except Exception as exc:  # pragma: no cover - exact import failures vary
        packages["mediapipe"] = {
            "imported": False,
            "version": None,
            "error": str(exc),
        }
        errors.append(f"MediaPipe import failed: {exc}")

    try:
        import numpy as np

        packages["numpy"] = {"imported": True, "version": str(np.__version__)}
    except Exception as exc:  # pragma: no cover - exact import failures vary
        packages["numpy"] = {
            "imported": False,
            "version": None,
            "error": str(exc),
        }
        errors.append(f"NumPy import failed: {exc}")

    opencv_distribution, opencv_distribution_version = _opencv_distribution()
    try:
        import cv2

        packages["opencv"] = {
            "imported": True,
            "version": str(cv2.__version__),
            "distribution": opencv_distribution,
            "distribution_version": opencv_distribution_version,
        }
    except Exception as exc:  # pragma: no cover - exact import failures vary
        packages["opencv"] = {
            "imported": False,
            "version": None,
            "distribution": opencv_distribution,
            "distribution_version": opencv_distribution_version,
            "error": str(exc),
        }
        errors.append(f"OpenCV import failed: {exc}")

    if opencv_distribution == "multiple":
        errors.append("Multiple OpenCV distributions are installed.")
    elif opencv_distribution is None:
        errors.append("No OpenCV distribution is installed.")

    if mp_module is not None:
        try:
            from mediapipe.tasks import python as tasks_python
            from mediapipe.tasks.python import vision

            mediapipe_api = inspect_mediapipe_api(
                mp_module,
                tasks_python,
                vision,
            )
        except Exception as exc:  # pragma: no cover - exact API failures vary
            errors.append(f"MediaPipe Tasks API import failed: {exc}")

    missing_api = [name for name, present in mediapipe_api.items() if not present]
    if missing_api:
        errors.append(
            "Required MediaPipe APIs are missing: " + ", ".join(missing_api)
        )

    directory_paths = {
        "models": config.MODELS_DIR,
        "input_images": config.INPUT_IMAGES_DIR,
        "input_videos": config.INPUT_VIDEOS_DIR,
        "output": config.OUTPUT_DIR,
    }
    directories = {
        name: check_directory(path) for name, path in directory_paths.items()
    }
    for name, result in directories.items():
        if not all(
            result[key]
            for key in (
                "exists",
                "is_directory",
                "readable",
                "writable",
                "deletable",
            )
        ):
            errors.append(f"Directory check failed for {name}: {result['path']}")

    pip_check = pip_check_runner()
    if not pip_check.get("ok", False):
        errors.append(
            f"pip check failed with exit code {pip_check.get('returncode')}."
        )

    for label, model_path in (
        ("Face Landmarker", config.FACE_LANDMARKER_MODEL_PATH),
        ("Pose Landmarker", config.POSE_LANDMARKER_MODEL_PATH),
    ):
        if not model_path.is_file():
            warnings.append(
                f"{label} model is not present yet (expected in a later phase): "
                f"{model_path}"
            )

    return {
        "schema_version": "1.0",
        "status": "failed" if errors else "ready",
        "platform": {
            "operating_system": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
        },
        "python": {
            "version": platform.python_version(),
            "version_info": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
                "micro": sys.version_info.micro,
            },
            "is_3_12": python_312,
            "executable": sys.executable,
            "pip_version": _package_version("pip"),
        },
        "virtual_environment": {
            "active": virtual_environment_active,
            "expected_root": str(EXPECTED_VENV_ROOT),
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "is_vision_server_environment": expected_environment,
        },
        "packages": packages,
        "mediapipe_api": mediapipe_api,
        "directories": directories,
        "pip_check": pip_check,
        "warnings": warnings,
        "errors": errors,
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    """Atomically write strict, readable UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Validate MediaPipe imports, Tasks APIs, directories, and pip "
            "consistency without loading a model."
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    report = collect_environment_report()
    try:
        write_report(report, REPORT_PATH)
    except (OSError, TypeError, ValueError) as exc:
        print(f"Failed to write environment report: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Environment report: {REPORT_PATH}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
