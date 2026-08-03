from __future__ import annotations

from pathlib import Path
import re
import unittest


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ANALYSIS_ROOT.parents[1]
DOCKERFILE = (ANALYSIS_ROOT / "Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = (ANALYSIS_ROOT / ".dockerignore").read_text(encoding="utf-8")
REQUIREMENTS = (ANALYSIS_ROOT / "requirements-docker.txt").read_text(encoding="utf-8")
COMPOSE = (WORKSPACE_ROOT / "docker-compose.local.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ANALYSIS_ROOT / ".env.docker.example").read_text(encoding="utf-8")
SMOKE = (ANALYSIS_ROOT / "scripts" / "smoke_analysis_api_container.py").read_text(
    encoding="utf-8"
)


class DockerfileContractTests(unittest.TestCase):
    def test_python_312_patch_is_pinned(self) -> None:
        self.assertIn("FROM python:3.12.10-slim-bookworm", DOCKERFILE)

    def test_runtime_dependencies_are_minimal(self) -> None:
        self.assertIn("ffmpeg libgomp1", DOCKERFILE)
        self.assertNotIn("libgl1", DOCKERFILE)

    def test_runtime_requirements_are_installed(self) -> None:
        self.assertIn("pip install --no-cache-dir -r requirements-docker.txt", DOCKERFILE)

    def test_non_root_facefit_user(self) -> None:
        self.assertIn("useradd --system --gid facefit", DOCKERFILE)
        self.assertRegex(DOCKERFILE, r"(?m)^USER facefit$")
        self.assertNotRegex(DOCKERFILE, r"(?m)^USER root$")

    def test_output_job_and_lock_directories_are_created(self) -> None:
        self.assertIn("/app/data/output/analysis_api/jobs", DOCKERFILE)
        self.assertIn("/app/data/output/analysis_api/locks", DOCKERFILE)

    def test_port_healthcheck_and_command(self) -> None:
        self.assertIn("EXPOSE 8002", DOCKERFILE)
        self.assertIn("HEALTHCHECK", DOCKERFILE)
        self.assertIn("http://127.0.0.1:8002/health", DOCKERFILE)
        self.assertIn('"uvicorn", "app.main:app"', DOCKERFILE)

    def test_model_and_output_are_not_copied_explicitly(self) -> None:
        self.assertNotRegex(DOCKERFILE, r"(?i)COPY\s+.*(?:models|data/output|\.env)")


class BuildContextContractTests(unittest.TestCase):
    def test_models_are_excluded(self) -> None:
        self.assertIn("models/", DOCKERIGNORE.splitlines())

    def test_all_repository_data_is_excluded(self) -> None:
        self.assertIn("data/", DOCKERIGNORE.splitlines())

    def test_environment_and_caches_are_excluded(self) -> None:
        for entry in (".env", ".env.*", "huggingface/", ".cache/", ".venv/"):
            self.assertIn(entry, DOCKERIGNORE.splitlines())

    def test_examples_are_allowed(self) -> None:
        self.assertIn("!.env.example", DOCKERIGNORE)
        self.assertIn("!.env.docker.example", DOCKERIGNORE)

    def test_tests_and_test_requirements_are_excluded(self) -> None:
        for entry in ("tests/", "runtime_tests/", "requirements-test.txt"):
            self.assertIn(entry, DOCKERIGNORE.splitlines())


class RequirementsContractTests(unittest.TestCase):
    def test_existing_runtime_requirement_groups_are_reused(self) -> None:
        self.assertEqual(
            REQUIREMENTS.splitlines(),
            ["-r requirements-api.txt", "-r requirements-stt.txt", "-r requirements-speech.txt"],
        )

    def test_test_and_unapproved_ml_dependencies_are_absent(self) -> None:
        lowered = REQUIREMENTS.lower()
        for dependency in ("pytest", "httpx", "torch", "openai-whisper"):
            self.assertNotIn(dependency, lowered)


class ComposeContractTests(unittest.TestCase):
    def test_vision_service_and_port_are_preserved(self) -> None:
        self.assertIn("  vision-server:", COMPOSE)
        self.assertIn('      - "8000:8000"', COMPOSE)

    def test_analysis_service_build_and_port(self) -> None:
        self.assertIn("  analysis-server:", COMPOSE)
        self.assertIn("context: ./ai-server/analysis-server", COMPOSE)
        self.assertIn('      - "8002:8002"', COMPOSE)

    def test_analysis_output_volume(self) -> None:
        self.assertIn(
            "./ai-server/analysis-server/data/output:/app/data/output", COMPOSE
        )

    def test_model_cache_is_read_only_and_not_host_specific(self) -> None:
        self.assertRegex(
            COMPOSE,
            r"\$\{FACEFIT_STT_MODEL_CACHE_HOST[^}]*\}:/models/faster-whisper:ro",
        )
        self.assertNotRegex(COMPOSE.lower(), r"[a-z]:[/\\]users[/\\]")

    def test_model_cache_environment_is_offline(self) -> None:
        self.assertIn('HF_HOME: "/models/faster-whisper"', COMPOSE)
        self.assertIn('HF_HUB_OFFLINE: "1"', COMPOSE)

    def test_worker_queue_and_retention_defaults(self) -> None:
        expected = {
            "ANALYSIS_API_JOB_MAX_WORKERS": "1",
            "ANALYSIS_API_JOB_QUEUE_CAPACITY": "16",
            "ANALYSIS_API_JOB_LOCK_WAIT_SECONDS": "300",
            "ANALYSIS_API_STALE_LOCK_SECONDS": "900",
            "ANALYSIS_API_SHUTDOWN_WAIT_SECONDS": "30",
            "ANALYSIS_API_JOB_RETENTION_ENABLED": "false",
            "ANALYSIS_API_JOB_RETENTION_DAYS": "30",
            "ANALYSIS_API_JOB_MAX_RECORDS": "1000",
        }
        for name, value in expected.items():
            self.assertIn(f'{name}: "{value}"', COMPOSE)

    def test_wildcard_cors_is_not_configured(self) -> None:
        self.assertIn('ANALYSIS_API_ALLOWED_ORIGINS: ""', COMPOSE)
        self.assertNotIn('ANALYSIS_API_ALLOWED_ORIGINS: "*"', COMPOSE)

    def test_healthcheck_uses_liveness_only(self) -> None:
        analysis = COMPOSE.split("  analysis-server:", 1)[1]
        self.assertIn("http://127.0.0.1:8002/health", analysis)
        self.assertNotIn("8002/ready", analysis)

    def test_both_services_share_the_named_network(self) -> None:
        self.assertEqual(COMPOSE.count("      - face-fit-ai-network"), 2)
        self.assertIn("name: face-fit-ai-network", COMPOSE)

    def test_graceful_shutdown_exceeds_application_wait(self) -> None:
        self.assertIn("stop_grace_period: 35s", COMPOSE)


class EnvironmentExampleTests(unittest.TestCase):
    def test_only_sanitized_model_cache_variable_is_present(self) -> None:
        assignments = [line for line in ENV_EXAMPLE.splitlines() if line and not line.startswith("#")]
        self.assertEqual(len(assignments), 1)
        self.assertTrue(assignments[0].startswith("FACEFIT_STT_MODEL_CACHE_HOST="))
        self.assertIn("replace/with/local", assignments[0])

    def test_no_secret_or_personal_path(self) -> None:
        lowered = ENV_EXAMPLE.lower()
        for token in ("token=", "password=", "c:/users/", "c:\\users\\"):
            self.assertNotIn(token, lowered)


class ContainerSmokeContractTests(unittest.TestCase):
    def test_smoke_does_not_manage_containers(self) -> None:
        self.assertNotRegex(SMOKE, r"subprocess|docker\s+compose|docker\s+run")

    def test_polling_is_bounded(self) -> None:
        self.assertIn('default=120.0', SMOKE)
        self.assertIn('default=0.25', SMOKE)
        self.assertIn("time.monotonic() + args.timeout_seconds", SMOKE)

    def test_required_endpoints_and_job_pipeline_are_exercised(self) -> None:
        for value in (
            '"/health"', '"/ready"', '"/openapi.json"',
            '"/api/v1/analysis/jobs"', '"STT_AND_SPEECH"',
            '/transcription"', '/speech-characteristics"',
        ):
            self.assertIn(value, SMOKE)

    def test_strict_json_and_protection_checks_exist(self) -> None:
        self.assertIn("parse_constant=_reject_constant", SMOKE)
        self.assertIn("allow_nan=False", SMOKE)
        for token in ("participantid", "filepath", "stacktrace", "/models/faster-whisper"):
            self.assertIn(token, SMOKE)


if __name__ == "__main__":
    unittest.main()
