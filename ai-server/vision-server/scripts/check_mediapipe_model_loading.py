"""Create and close each MediaPipe IMAGE-mode landmarker once."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.landmarker_factory import (  # noqa: E402
    LandmarkerFactoryError,
    create_face_landmarker_image_mode,
    create_pose_landmarker_image_mode,
)
from app.vision.model_registry import (  # noqa: E402
    MANIFEST_PATH,
    ModelRegistryError,
    get_model_descriptor,
    require_model_ready,
    write_json_atomic,
)


REPORT_PATH = VISION_SERVER_ROOT / "model_loading_report.json"


def _empty_model_result(model_id: str) -> dict[str, Any]:
    descriptor = get_model_descriptor(model_id)
    return {
        "status": "failed",
        "path": str(descriptor.local_path.resolve(strict=False)),
        "sha256": None,
        "load_time_sec": 0.0,
        "closed": False,
    }


def _load_and_close(
    model_id: str,
    creator: Callable[[], Any],
    failure_code: str,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    result = _empty_model_result(model_id)
    try:
        descriptor = get_model_descriptor(model_id)
        state = require_model_ready(descriptor, MANIFEST_PATH)
        result["sha256"] = state["sha256"]
        started = time.perf_counter()
        landmarker = creator()
        result["load_time_sec"] = round(time.perf_counter() - started, 6)
        try:
            landmarker.close()
            result["closed"] = True
            result["status"] = "loaded"
        finally:
            if not result["closed"]:
                try:
                    landmarker.close()
                    result["closed"] = True
                except Exception:
                    pass
        return result, None
    except (ModelRegistryError, LandmarkerFactoryError) as exc:
        return result, {"code": exc.code, "message": str(exc)}
    except Exception as exc:
        return result, {
            "code": failure_code,
            "message": f"{model_id} creation failed: {exc}",
        }


def check_model_loading(
    face_creator: Callable[[], Any] = create_face_landmarker_image_mode,
    pose_creator: Callable[[], Any] = create_pose_landmarker_image_mode,
) -> dict[str, Any]:
    face_result, face_error = _load_and_close(
        "face_landmarker",
        face_creator,
        "FACE_MODEL_LOAD_FAILED",
    )
    pose_result, pose_error = _load_and_close(
        "pose_landmarker",
        pose_creator,
        "POSE_MODEL_LOAD_FAILED",
    )
    errors = [error for error in (face_error, pose_error) if error is not None]
    temporary_files = sorted(
        str(path)
        for pattern in ("*.part", ".*.tmp")
        for path in (VISION_SERVER_ROOT / "models").glob(pattern)
    )
    if temporary_files:
        errors.append(
            {
                "code": "MEDIAPIPE_MODEL_SETUP_FAILED",
                "message": "Temporary model files remain after loading.",
            }
        )
    return {
        "schema_version": "1.0",
        "status": "ready" if not errors else "failed",
        "face_model": face_result,
        "pose_model": pose_result,
        "warnings": [],
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Create and close Face/Pose IMAGE-mode landmarkers without inference."
        )
    )


def main(argv: list[str] | None = None) -> int:
    try:
        build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    report = check_model_loading()
    try:
        write_json_atomic(report, REPORT_PATH)
    except (OSError, TypeError, ValueError) as exc:
        print(
            f"MODEL_LOADING_REPORT_WRITE_FAILED: {exc}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Model loading report: {REPORT_PATH}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
