"""Validate the complete Stage 29 Backend handoff package without extra deps."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Sequence


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import export_ai_contracts as exporter  # noqa: E402


REQUIRED_FILES = {
    "README.md",
    "contracts/common-job-contract.schema.json",
    "contracts/vision-job-request.schema.json",
    "contracts/vision-job-response.schema.json",
    "contracts/analysis-job-request.schema.json",
    "contracts/analysis-job-response.schema.json",
    "contracts/vision-feedback.schema.json",
    "contracts/transcription-response.schema.json",
    "contracts/speech-characteristics-response.schema.json",
    "contracts/integrated-session.schema.json",
    "examples/vision-job-request.json",
    "examples/vision-job-response.json",
    "examples/analysis-job-request.json",
    "examples/analysis-job-response.json",
    "examples/vision-feedback.json",
    "examples/transcription-response-redacted.json",
    "examples/speech-characteristics-response.json",
    "examples/integrated-session-response.json",
    "examples/common-error-response.json",
    "examples/common-warning.json",
    "docs/backend-integration-guide.md",
    "docs/polling-and-retry-policy.md",
    "docs/error-warning-reference.md",
    "docs/environment-and-docker-guide.md",
    "docs/ai-development-completion-report.md",
    "scripts/export_ai_contracts.py",
    "scripts/validate_handoff_package.py",
    "tests/test_backend_handoff_stage29.py",
}

EXAMPLE_SCHEMA = {
    "vision-job-request.json": "vision-job-request.schema.json",
    "vision-job-response.json": "vision-job-response.schema.json",
    "analysis-job-request.json": "analysis-job-request.schema.json",
    "analysis-job-response.json": "analysis-job-response.schema.json",
    "vision-feedback.json": "vision-feedback.schema.json",
    "transcription-response-redacted.json": "transcription-response.schema.json",
    "speech-characteristics-response.json": "speech-characteristics-response.schema.json",
    "integrated-session-response.json": "integrated-session.schema.json",
}

VISION_ERROR_CODES = {
    "VALIDATION_ERROR", "SESSION_NOT_FOUND", "JOB_NOT_FOUND", "RESULT_NOT_READY",
    "UNSUPPORTED_ANALYSIS_MODE", "INPUT_ARTIFACTS_MISSING", "FEEDBACK_BUILD_FAILED",
    "DEPENDENCY_UNAVAILABLE", "JOB_STORAGE_ERROR", "INTERNAL_SERVER_ERROR",
}
ANALYSIS_ERROR_CODES = {
    "VALIDATION_ERROR", "SESSION_NOT_FOUND", "JOB_NOT_FOUND", "RESULT_NOT_READY",
    "UNSUPPORTED_PIPELINE", "INPUT_ARTIFACTS_MISSING", "TRANSCRIPTION_FAILED",
    "SPEECH_ANALYSIS_FAILED", "DEPENDENCY_UNAVAILABLE", "JOB_STORAGE_ERROR",
    "JOB_QUEUE_FULL", "INVALID_JOB_STATE_TRANSITION", "INTERNAL_SERVER_ERROR",
}
INTEGRATION_ERROR_CODES = {
    "SESSION_ID_MISMATCH", "ANSWER_SET_MISMATCH", "ANSWER_INTERVAL_MISMATCH",
    "TIMESTAMP_OUT_OF_RANGE", "COMPONENT_RESULT_NOT_READY", "COMPONENT_JOB_FAILED",
    "COMPONENT_HTTP_ERROR", "COMPONENT_RESPONSE_INVALID", "INTEGRATION_TIMEOUT",
}
WARNING_CODES = {
    "HEAD_POSE_PARTIAL_AVAILABILITY", "SEGMENT_BOUNDARY_EXPANDED_TO_WORDS",
    "UPSTREAM_TRANSCRIPTION_WARNING", "FILLER_CANDIDATE_REVIEW_REQUIRED",
    "ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED",
}
FORBIDDEN_KEYS = {
    "participantid", "participant_id", "consent", "metadata", "raterid", "rater_id",
    "absolutepath", "absolute_path", "videofilename", "video_filename",
    "modelcachepath", "model_cache_path", "score", "grade", "passprobability",
    "pass_probability", "confidence", "anxiety", "personality", "emotion",
}


class HandoffValidationError(ValueError):
    pass


def strict_load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise HandoffValidationError(f"Unsupported schema type {expected}")


def validate_instance(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "anyOf" in schema:
        failures = []
        for candidate in schema["anyOf"]:
            try:
                validate_instance(value, candidate, path)
                return
            except HandoffValidationError as exc:
                failures.append(str(exc))
        raise HandoffValidationError(f"{path} does not match anyOf")
    if "const" in schema and value != schema["const"]:
        raise HandoffValidationError(f"{path} does not match const")
    if "enum" in schema and value not in schema["enum"]:
        raise HandoffValidationError(f"{path} is not in enum")
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        raise HandoffValidationError(f"{path} must be {expected}")
    if isinstance(value, float) and not math.isfinite(value):
        raise HandoffValidationError(f"{path} is not finite")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise HandoffValidationError(f"{path} is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise HandoffValidationError(f"{path} does not match pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise HandoffValidationError(f"{path} is less than minimum")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise HandoffValidationError(f"{path} has too few items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_instance(item, item_schema, f"{path}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise HandoffValidationError(f"{path} missing {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise HandoffValidationError(f"{path} has extra properties {sorted(extras)}")
        for key, item in value.items():
            child = properties.get(key)
            if isinstance(child, dict):
                validate_instance(item, child, f"{path}.{key}")


def validate_schema_document(schema: dict[str, Any], name: str) -> None:
    if schema.get("$schema") != exporter.SCHEMA_URI:
        raise HandoffValidationError(f"{name} has the wrong JSON Schema dialect")
    if schema.get("type") != "object":
        raise HandoffValidationError(f"{name} root must be object")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and "additionalProperties" not in value:
                raise HandoffValidationError(f"{name}:{path} lacks additionalProperties policy")
            required = value.get("required")
            if required is not None:
                if not isinstance(required, list) or len(required) != len(set(required)):
                    raise HandoffValidationError(f"{name}:{path} has invalid required fields")
                properties = value.get("properties", {})
                if not set(required).issubset(set(properties)):
                    raise HandoffValidationError(f"{name}:{path} requires undefined fields")
            enum = value.get("enum")
            if enum is not None and len(enum) != len(set(enum)):
                raise HandoffValidationError(f"{name}:{path} has duplicate enum values")
            pattern = value.get("pattern")
            if pattern is not None:
                re.compile(pattern)
            for key, item in value.items():
                walk(item, f"{path}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}/{index}")

    walk(schema, "$")


def validate_privacy(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.replace("-", "_").lower()
            if normalized in FORBIDDEN_KEYS:
                raise HandoffValidationError(f"Forbidden field {path}.{key}")
            if normalized == "scores" and item is not None:
                raise HandoffValidationError("Vision scores must be null")
            if normalized == "text" and item is not None:
                raise HandoffValidationError("Transcript example text must be null")
            validate_privacy(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_privacy(item, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            re.search(r"\bPTC_\d{6}\b", value)
            or re.search(r"(?:^|\s)[A-Za-z]:[\\/]", value)
            or lowered.startswith("/app/")
            or lowered.startswith("/data/")
            or "/models/" in lowered
            or "private transcript" in lowered
        ):
            raise HandoffValidationError(f"Sensitive value at {path}")


def validate_error_example(value: dict[str, Any]) -> None:
    expected = {"code", "message", "requestId", "details"}
    if set(value) != expected or not isinstance(value["details"], list):
        raise HandoffValidationError("Common error example is invalid")
    if re.fullmatch(exporter.UUID_PATTERN, value["requestId"]) is None:
        raise HandoffValidationError("Common error requestId is invalid")


def _assert_doc_contains(path: Path, values: set[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = sorted(value for value in values if value not in text)
    if missing:
        raise HandoffValidationError(f"{path.name} is missing {missing}")


def validate_package(
    handoff_root: Path,
    *,
    repo_root: Path | None = None,
    vision_python: Path | None = None,
    analysis_python: Path | None = None,
    verify_openapi: bool = True,
) -> dict[str, Any]:
    missing = sorted(path for path in REQUIRED_FILES if not (handoff_root / path).is_file())
    if missing:
        raise HandoffValidationError(f"Required files are missing: {missing}")

    generated_schemas = exporter.schemas()
    generated_examples = exporter.examples()
    loaded_schemas: dict[str, dict[str, Any]] = {}
    for name, expected in generated_schemas.items():
        loaded = strict_load(handoff_root / "contracts" / name)
        if loaded != expected:
            raise HandoffValidationError(f"{name} does not match the deterministic export")
        validate_schema_document(loaded, name)
        loaded_schemas[name] = loaded

    loaded_examples: dict[str, dict[str, Any]] = {}
    for name, expected in generated_examples.items():
        loaded = strict_load(handoff_root / "examples" / name)
        if loaded != expected:
            raise HandoffValidationError(f"{name} does not match the deterministic export")
        validate_privacy(loaded)
        loaded_examples[name] = loaded

    for example_name, schema_name in EXAMPLE_SCHEMA.items():
        validate_instance(loaded_examples[example_name], loaded_schemas[schema_name])
    validate_error_example(loaded_examples["common-error-response.json"])
    validate_instance(loaded_examples["common-warning.json"], exporter._warning())

    reference = handoff_root / "docs" / "error-warning-reference.md"
    _assert_doc_contains(
        reference,
        VISION_ERROR_CODES | ANALYSIS_ERROR_CODES | INTEGRATION_ERROR_CODES | WARNING_CODES,
    )
    endpoint_docs = (
        (handoff_root / "README.md").read_text(encoding="utf-8")
        + (handoff_root / "docs" / "backend-integration-guide.md").read_text(encoding="utf-8")
    )
    for path in exporter.VISION_PATHS | exporter.ANALYSIS_PATHS:
        if path not in endpoint_docs:
            raise HandoffValidationError(f"Endpoint documentation is missing {path}")

    if verify_openapi:
        if repo_root is None:
            repo_root = handoff_root.parents[2]
        vision_root = repo_root / "ai-server" / "vision-server"
        analysis_root = repo_root / "ai-server" / "analysis-server"
        vision = exporter._load_openapi(
            vision_root, vision_python or exporter._default_python(vision_root)
        )
        analysis = exporter._load_openapi(
            analysis_root, analysis_python or exporter._default_python(analysis_root)
        )
        exporter.validate_openapi(vision, analysis)

    return {
        "status": "valid",
        "requiredFileCount": len(REQUIRED_FILES),
        "schemaCount": len(loaded_schemas),
        "exampleCount": len(loaded_examples),
        "validatedExampleCount": len(EXAMPLE_SCHEMA) + 2,
        "documentedErrorCodeCount": len(
            VISION_ERROR_CODES | ANALYSIS_ERROR_CODES | INTEGRATION_ERROR_CODES
        ),
        "documentedWarningCodeCount": len(WARNING_CODES),
        "openapiVerified": verify_openapi,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Validate Stage 29 Backend handoff package.")
    result.add_argument("--handoff-root", type=Path, default=SCRIPT_ROOT.parent)
    result.add_argument("--repo-root", type=Path)
    result.add_argument("--vision-python", type=Path)
    result.add_argument("--analysis-python", type=Path)
    result.add_argument("--skip-openapi", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = validate_package(
            args.handoff_root.resolve(),
            repo_root=args.repo_root.resolve() if args.repo_root else None,
            vision_python=args.vision_python,
            analysis_python=args.analysis_python,
            verify_openapi=not args.skip_openapi,
        )
    except (HandoffValidationError, RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "errorType": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
