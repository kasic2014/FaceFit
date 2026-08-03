from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.vision_api_config import (
    VisionApiConfigError,
    VisionApiSettings,
)
from app.services.vision_job_service import (
    FileJobStorage,
    VisionApiServiceError,
    VisionJobService,
    atomic_write_json,
    validate_feedback_contract,
    validate_job_id,
    validate_session_id,
)
from app.vision.pilot_video_intake import PilotVideoIntakeError
from app.vision.single_session_mvp_feedback import (
    ANALYSIS_MODE,
    RESULT_LIMITED,
    SCORING_REASONS,
)
from scripts.validate_vision_mvp_api import OUTPUT_NAMES, main as validate_main


SESSION_ID = "SES_900001"
JOB_IDS = (
    "10000000-0000-4000-8000-000000000001",
    "10000000-0000-4000-8000-000000000002",
    "10000000-0000-4000-8000-000000000003",
)


def _feedback() -> dict[str, object]:
    return {
        "sessionId": SESSION_ID,
        "status": RESULT_LIMITED,
        "analysisMode": ANALYSIS_MODE,
        "analysisScope": "FACE_AND_BOTH_SHOULDERS",
        "operational": False,
        "scores": None,
        "scoreUnavailableReasons": list(SCORING_REASONS),
        "measurementSummary": {},
        "answers": [],
        "warnings": [
            "일부 프레임에서 고개 방향 측정값을 계산하지 못했습니다."
        ],
        "limitations": [],
        "disclaimer": "fixture-only measurement disclaimer",
    }


def _record(job_id: str = JOB_IDS[0]) -> dict[str, object]:
    return {
        "jobId": job_id,
        "sessionId": SESSION_ID,
        "analysisMode": ANALYSIS_MODE,
        "forceRebuild": False,
        "status": "SUCCEEDED_WITH_LIMITATIONS",
        "createdAt": "2026-07-31T00:00:00Z",
        "startedAt": "2026-07-31T00:00:01Z",
        "completedAt": "2026-07-31T00:00:02Z",
        "resultAvailable": True,
        "warnings": [],
        "error": None,
    }


class SequenceClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 31, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        value = self.value
        self.value += timedelta(seconds=1)
        return value


class VisionApiFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.output = root / "data" / "output"
        (
            self.output
            / "pilot_video_intake_validation"
            / SESSION_ID
        ).mkdir(parents=True)
        feedback_path = (
            self.output
            / "single_session_mvp_feedback"
            / SESSION_ID
            / "mvp_feedback_api_contract.json"
        )
        atomic_write_json(feedback_path, _feedback())
        self.ids = iter(JOB_IDS)
        self.service = VisionJobService(
            vision_server_root=root,
            output_root=self.output,
            job_id_generator=lambda: next(self.ids),
            clock=SequenceClock(),
        )


class ConfigTests(unittest.TestCase):
    def test_defaults_do_not_enable_wildcard_cors(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = VisionApiSettings.from_env(
                vision_server_root=Path.cwd()
            )
        self.assertEqual(settings.allowed_origins, ())
        self.assertEqual(settings.port, 8000)
        self.assertTrue(settings.enable_docs)

    def test_production_disables_docs_by_default(self):
        with patch.dict(
            os.environ,
            {"VISION_API_ENV": "production"},
            clear=True,
        ):
            settings = VisionApiSettings.from_env(
                vision_server_root=Path.cwd()
            )
        self.assertFalse(settings.enable_docs)

    def test_wildcard_origin_is_rejected(self):
        with patch.dict(
            os.environ,
            {"VISION_API_ALLOWED_ORIGINS": "*"},
            clear=True,
        ):
            with self.assertRaises(VisionApiConfigError):
                VisionApiSettings.from_env(vision_server_root=Path.cwd())


class ValidationTests(unittest.TestCase):
    def test_session_and_job_ids_reject_path_traversal(self):
        for value in ("../SES_900001", "SES_900001/../../x", "SES_1"):
            with self.subTest(value=value):
                with self.assertRaises(VisionApiServiceError):
                    validate_session_id(value)
        with self.assertRaises(VisionApiServiceError):
            validate_job_id("../../job")

    def test_feedback_contract_canonicalizes_scoring_reasons(self):
        result = validate_feedback_contract(
            _feedback(),
            expected_session_id=SESSION_ID,
        )
        self.assertNotIn("scoreUnavailableReasons", result)
        self.assertEqual(
            result["scoringUnavailableReasons"],
            list(SCORING_REASONS),
        )
        self.assertIsNone(result["scores"])

    def test_feedback_rejects_participant_internal_path_and_scores(self):
        cases = (
            ("participantId", "PTC_900001"),
            ("diagnostic", r"C:\private\result.json"),
            ("gazeScore", 10),
        )
        for key, value in cases:
            payload = _feedback()
            payload[key] = value
            with self.subTest(key=key):
                with self.assertRaises(VisionApiServiceError):
                    validate_feedback_contract(
                        payload,
                        expected_session_id=SESSION_ID,
                    )

    def test_feedback_rejects_nan_and_infinity(self):
        for value in (float("nan"), float("inf")):
            payload = _feedback()
            payload["measurementSummary"] = {"bad": value}
            with self.subTest(value=value):
                with self.assertRaises(PilotVideoIntakeError):
                    validate_feedback_contract(
                        payload,
                        expected_session_id=SESSION_ID,
                    )


class StorageTests(unittest.TestCase):
    def test_atomic_job_storage_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = FileJobStorage(root)
            storage.save_new(_record())
            loaded = FileJobStorage(root).load(JOB_IDS[0])
        self.assertEqual(loaded, _record())

    def test_atomic_write_uses_replace_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "job.json"
            real_replace = os.replace
            with patch(
                "app.services.vision_job_service.os.replace",
                wraps=real_replace,
            ) as replace:
                atomic_write_json(destination, _record())
            self.assertEqual(replace.call_count, 1)
            self.assertEqual(
                list(Path(directory).glob(".*.tmp")),
                [],
            )

    def test_job_id_collision_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = FileJobStorage(directory)
            storage.save_new(_record())
            with self.assertRaises(VisionApiServiceError) as raised:
                storage.save_new(_record())
        self.assertEqual(raised.exception.code, "JOB_STORAGE_ERROR")

    def test_corrupted_job_json_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{JOB_IDS[0]}.json"
            path.write_text('{"status": NaN}', encoding="utf-8")
            with self.assertRaises(VisionApiServiceError) as raised:
                FileJobStorage(directory).load(JOB_IDS[0])
        self.assertEqual(raised.exception.code, "JOB_STORAGE_ERROR")

    def test_nonfinite_job_json_is_not_written(self):
        with tempfile.TemporaryDirectory() as directory:
            record = _record()
            record["warnings"] = [{"value": float("nan")}]
            with self.assertRaises(PilotVideoIntakeError):
                FileJobStorage(directory).save_new(record)
            self.assertEqual(list(Path(directory).glob("*.json")), [])


class ServiceTests(unittest.TestCase):
    def test_job_creation_maps_measurement_limitations(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = VisionApiFixture(Path(directory))
            job = fixture.service.create_job(
                session_id=SESSION_ID,
                analysis_mode=ANALYSIS_MODE,
            )
        self.assertEqual(job["status"], "SUCCEEDED_WITH_LIMITATIONS")
        self.assertTrue(job["resultAvailable"])
        self.assertEqual(
            job["warnings"][0]["code"],
            "HEAD_POSE_PARTIAL_AVAILABILITY",
        )
        self.assertNotIn("forceRebuild", job)

    def test_successful_non_force_request_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = VisionApiFixture(Path(directory))
            first = fixture.service.create_job(
                session_id=SESSION_ID,
                analysis_mode=ANALYSIS_MODE,
            )
            second = fixture.service.create_job(
                session_id=SESSION_ID,
                analysis_mode=ANALYSIS_MODE,
            )
        self.assertEqual(first["jobId"], second["jobId"])

    def test_running_request_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = VisionApiFixture(Path(directory))
            running = _record()
            running["status"] = "RUNNING"
            running["completedAt"] = None
            running["resultAvailable"] = False
            fixture.service.storage.save_new(running)
            result = fixture.service.create_job(
                session_id=SESSION_ID,
                analysis_mode=ANALYSIS_MODE,
            )
        self.assertEqual(result["jobId"], JOB_IDS[0])
        self.assertEqual(result["status"], "RUNNING")

    def test_force_rebuild_creates_distinct_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = VisionApiFixture(Path(directory))
            with patch.object(
                fixture.service,
                "rebuild_feedback",
                side_effect=lambda session_id: validate_feedback_contract(
                    _feedback(),
                    expected_session_id=session_id,
                ),
            ):
                first = fixture.service.create_job(
                    session_id=SESSION_ID,
                    analysis_mode=ANALYSIS_MODE,
                    force_rebuild=True,
                )
                second = fixture.service.create_job(
                    session_id=SESSION_ID,
                    analysis_mode=ANALYSIS_MODE,
                    force_rebuild=True,
                )
        self.assertNotEqual(first["jobId"], second["jobId"])

    def test_missing_session_is_404(self):
        with tempfile.TemporaryDirectory() as directory:
            service = VisionJobService(
                vision_server_root=directory,
                output_root=Path(directory) / "data" / "output",
            )
            with self.assertRaises(VisionApiServiceError) as raised:
                service.load_feedback(SESSION_ID)
        self.assertEqual(
            (raised.exception.status_code, raised.exception.code),
            (404, "SESSION_NOT_FOUND"),
        )

    def test_registered_session_without_result_is_409(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "output"
            (
                output
                / "pilot_video_intake_validation"
                / SESSION_ID
            ).mkdir(parents=True)
            service = VisionJobService(
                vision_server_root=directory,
                output_root=output,
            )
            with self.assertRaises(VisionApiServiceError) as raised:
                service.load_feedback(SESSION_ID)
        self.assertEqual(
            (raised.exception.status_code, raised.exception.code),
            (409, "RESULT_NOT_READY"),
        )

    def test_unknown_analysis_mode_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = VisionApiFixture(Path(directory))
            with self.assertRaises(VisionApiServiceError) as raised:
                fixture.service.create_job(
                    session_id=SESSION_ID,
                    analysis_mode="FULL_PIPELINE",
                )
        self.assertEqual(raised.exception.code, "UNSUPPORTED_ANALYSIS_MODE")

    def test_unknown_job_is_404(self):
        with tempfile.TemporaryDirectory() as directory:
            service = VisionJobService(
                vision_server_root=directory,
                output_root=Path(directory) / "data" / "output",
            )
            with self.assertRaises(VisionApiServiceError) as raised:
                service.get_job(JOB_IDS[0])
        self.assertEqual(raised.exception.code, "JOB_NOT_FOUND")

    def test_readiness_checks_storage_without_session_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "output"
            service = VisionJobService(
                vision_server_root=directory,
                output_root=output,
            )
            service.check_readiness()
        self.assertTrue(True)


class StaticApiContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_required_routes_and_openapi_metadata_are_declared(self):
        main = (self.root / "app" / "main.py").read_text(encoding="utf-8")
        health = (
            self.root / "app" / "api" / "routers" / "health.py"
        ).read_text(encoding="utf-8")
        jobs = (
            self.root / "app" / "api" / "routers" / "vision_jobs.py"
        ).read_text(encoding="utf-8")
        self.assertIn('title="Face-Fit Vision MVP API"', main)
        self.assertIn('"/health"', health)
        self.assertIn('"/ready"', health)
        self.assertIn('prefix="/api/v1/vision"', jobs)
        self.assertIn('"/jobs"', jobs)
        self.assertIn('"/jobs/{job_id}"', jobs)
        self.assertIn('"/sessions/{session_id}/feedback"', jobs)

    def test_legacy_path_endpoint_no_longer_accepts_image_path(self):
        main = (self.root / "app" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("image_path", main)
        self.assertNotIn("allow_origins=[\"*\"]", main)
        self.assertIn('"/api/v1/analyze/image"', main)

    def test_docker_context_excludes_models_inputs_and_outputs(self):
        ignored = (self.root / ".dockerignore").read_text(encoding="utf-8")
        for entry in ("models/", "data/input/", "data/pilot/", "data/output/"):
            self.assertIn(entry, ignored)
        dockerfile = (self.root / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER facefit", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)

    def test_runtime_dependencies_remain_declared(self):
        requirements = (self.root / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("fastapi", requirements)
        self.assertIn("uvicorn", requirements)
        self.assertIn("pydantic", requirements)

    def test_uvicorn_smoke_script_always_stops_process(self):
        smoke = (
            self.root / "scripts" / "smoke_vision_mvp_uvicorn.py"
        ).read_text(encoding="utf-8")
        self.assertIn("finally:", smoke)
        self.assertIn("process.terminate()", smoke)
        self.assertIn("process.kill()", smoke)
        self.assertIn("port_left_occupied", smoke)


class ValidationArtifactTests(unittest.TestCase):
    def test_blocked_runtime_outputs_are_explicit_and_strict(self):
        missing = lambda name: {
            "name": name,
            "declared_requirement": f"{name}>=fixture",
            "installed_version": None,
            "importable": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation"
            with patch(
                "scripts.validate_vision_mvp_api._package_state",
                side_effect=missing,
            ):
                exit_code = validate_main(
                    [
                        "--vision-root",
                        str(Path(__file__).resolve().parents[1]),
                        "--output-dir",
                        str(output),
                        "--docker-static-status",
                        "PASSED",
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(OUTPUT_NAMES),
            )
            status = json.loads(
                (output / "api_validation_status.json").read_text(
                    encoding="utf-8"
                ),
                parse_constant=lambda value: self.fail(value),
            )
        self.assertEqual(
            status["status"],
            "vision_api_code_ready_runtime_dependency_blocked",
        )
        self.assertFalse(status["runtime_verified"])
