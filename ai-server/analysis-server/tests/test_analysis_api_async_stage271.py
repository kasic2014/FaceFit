from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest

from app.audio.audio_manifest_writer import write_json_atomic
from app.core.analysis_api_config import AnalysisApiConfig
from app.services.analysis_job_lock import AnalysisJobLockManager, JobLockError
from app.services.analysis_job_retention import AnalysisJobRetention
from app.services.analysis_job_service import AnalysisApiServiceError, AnalysisJobService
from app.services.analysis_job_storage import AnalysisJobStorage
from app.stt.transcription_profile import CPU_INT8
from tests.test_analysis_api_stage27 import seed_results


def make_config(root: Path, **changes) -> AnalysisApiConfig:
    values = {
        "environment": "test",
        "host": "127.0.0.1",
        "port": 8002,
        "allowed_origins": (),
        "enable_docs": True,
        "output_root": root,
        "log_level": "INFO",
        "expose_transcript_text": True,
        "job_max_workers": 1,
        "job_queue_capacity": 16,
        "job_lock_wait_seconds": 1,
        "stale_lock_seconds": 60,
        "shutdown_wait_seconds": 1,
        "job_retention_enabled": False,
        "job_retention_days": 30,
        "job_max_records": 1000,
    }
    values.update(changes)
    return AnalysisApiConfig(**values)


def wait_job(service: AnalysisJobService, job_id: str, statuses: set[str], timeout: float = 3) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job["status"] in statuses:
            return job
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} did not reach {statuses}")


def record(job_id: str, status: str, at: datetime, *, session: str = "SES_000001") -> dict:
    stamp = at.isoformat().replace("+00:00", "Z")
    started = stamp if status == "RUNNING" else None
    completed = stamp if status in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"} else None
    return {
        "jobId": job_id,
        "sessionId": session,
        "pipeline": "SPEECH_CHARACTERISTICS",
        "forceRebuild": True,
        "status": status,
        "createdAt": stamp,
        "queuedAt": stamp,
        "startedAt": started,
        "completedAt": completed,
        "updatedAt": stamp,
        "queueWaitMs": 0 if started else None,
        "executionDurationMs": 0 if completed and started else None,
        "totalDurationMs": 0 if completed else None,
        "resultAvailable": status in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"},
        "warnings": [],
        "error": ({"code": "TEST", "message": "failed", "httpStatus": 500} if status == "FAILED" else None),
    }


class AsyncExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        seed_results(self.root)
        self.services: list[AnalysisJobService] = []

    def tearDown(self) -> None:
        for service in self.services:
            try:
                service.shutdown()
            except Exception:
                pass
        self.temp.cleanup()

    def service(self, **kwargs) -> AnalysisJobService:
        config_changes = kwargs.pop("config_changes", {})
        service = AnalysisJobService(make_config(self.root, **config_changes), **kwargs)
        self.services.append(service)
        service.start()
        return service

    def test_post_contract_returns_queued_before_blocked_work_finishes(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def runner(session_id: str, force: bool) -> dict:
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        service = self.service(speech_runner=runner)
        started = time.perf_counter()
        created = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", False)
        elapsed = time.perf_counter() - started
        self.assertEqual(created["status"], "QUEUED")
        self.assertLess(elapsed, 0.25)
        self.assertTrue(entered.wait(1))
        running = wait_job(service, created["jobId"], {"RUNNING"})
        self.assertIsNotNone(running["startedAt"])
        release.set()
        done = wait_job(service, created["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        self.assertTrue(done["resultAvailable"])
        self.assertGreaterEqual(done["queueWaitMs"], 0)
        self.assertGreaterEqual(done["executionDurationMs"], 0)
        self.assertGreaterEqual(done["totalDurationMs"], done["executionDurationMs"])
        ordered = [done[key] for key in ("createdAt", "queuedAt", "startedAt", "completedAt")]
        self.assertEqual(ordered, sorted(ordered))

    def test_runner_failure_becomes_failed_and_releases_lock(self) -> None:
        def fail(session_id: str, force: bool) -> dict:
            raise RuntimeError("private failure")

        service = self.service(speech_runner=fail)
        created = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        failed = wait_job(service, created["jobId"], {"FAILED"})
        self.assertEqual(failed["error"]["code"], "INTERNAL_SERVER_ERROR")
        self.assertNotIn("private failure", str(failed))
        self.assertFalse(any((self.root / "analysis_api" / "locks").glob("SES_*.lock")))

    def test_concurrent_identical_requests_create_one_job_and_one_execution(self) -> None:
        entered, release = threading.Event(), threading.Event()
        call_count = 0
        call_lock = threading.Lock()

        def runner(session_id: str, force: bool) -> dict:
            nonlocal call_count
            with call_lock:
                call_count += 1
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        service = self.service(speech_runner=runner)
        barrier = threading.Barrier(8)
        ids: list[str] = []
        errors: list[Exception] = []

        def request() -> None:
            try:
                barrier.wait()
                ids.append(service.create_job(
                    "SES_000001", "SPEECH_CHARACTERISTICS", False
                )["jobId"])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=request) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertFalse(errors)
        self.assertEqual(len(set(ids)), 1)
        self.assertTrue(entered.wait(1))
        release.set()
        wait_job(service, ids[0], {"SUCCEEDED_WITH_WARNINGS"})
        self.assertEqual(call_count, 1)
        self.assertEqual(len(service.storage.list_records()), 1)

    def test_two_service_instances_use_file_guard_for_one_non_force_job(self) -> None:
        entered, release = threading.Event(), threading.Event()
        calls = 0
        calls_lock = threading.Lock()

        def runner(session_id: str, force: bool) -> dict:
            nonlocal calls
            with calls_lock:
                calls += 1
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        first = self.service(speech_runner=runner)
        second = self.service(speech_runner=runner)
        barrier = threading.Barrier(2)
        jobs: list[dict] = []

        def request(service: AnalysisJobService) -> None:
            barrier.wait()
            jobs.append(service.create_job(
                "SES_000001", "SPEECH_CHARACTERISTICS", False
            ))

        threads = [
            threading.Thread(target=request, args=(first,)),
            threading.Thread(target=request, args=(second,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(len({job["jobId"] for job in jobs}), 1)
        self.assertTrue(entered.wait(1))
        release.set()
        wait_job(first, jobs[0]["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        self.assertEqual(calls, 1)

    def test_force_jobs_are_distinct_but_same_key_execution_is_serialized(self) -> None:
        first_entered, release = threading.Event(), threading.Event()
        state_lock = threading.Lock()
        active = 0
        maximum = 0
        calls = 0

        def runner(session_id: str, force: bool) -> dict:
            nonlocal active, maximum, calls
            with state_lock:
                active += 1
                calls += 1
                maximum = max(maximum, active)
                current = calls
            if current == 1:
                first_entered.set()
                release.wait(2)
            with state_lock:
                active -= 1
            return {"status": "ready"}

        service = self.service(
            speech_runner=runner,
            config_changes={"job_max_workers": 2},
        )
        first = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertTrue(first_entered.wait(1))
        second = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertNotEqual(first["jobId"], second["jobId"])
        release.set()
        wait_job(service, first["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        wait_job(service, second["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        self.assertEqual(maximum, 1)

    def test_different_sessions_can_use_two_workers(self) -> None:
        seed_results(self.root, "SES_000002")
        both_entered = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        active = 0

        def runner(session_id: str, force: bool) -> dict:
            nonlocal active
            with lock:
                active += 1
                if active == 2:
                    both_entered.set()
            release.wait(2)
            with lock:
                active -= 1
            return {"status": "ready"}

        service = self.service(
            speech_runner=runner,
            config_changes={"job_max_workers": 2},
        )
        one = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        two = service.create_job("SES_000002", "SPEECH_CHARACTERISTICS", True)
        self.assertTrue(both_entered.wait(1))
        release.set()
        wait_job(service, one["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        wait_job(service, two["jobId"], {"SUCCEEDED_WITH_WARNINGS"})

    def test_queue_full_returns_503_without_incomplete_record(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def runner(session_id: str, force: bool) -> dict:
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        service = self.service(
            speech_runner=runner,
            config_changes={"job_queue_capacity": 1},
        )
        service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertTrue(entered.wait(1))
        service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        with self.assertRaises(AnalysisApiServiceError) as raised:
            service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertEqual((raised.exception.code, raised.exception.status_code), ("JOB_QUEUE_FULL", 503))
        self.assertEqual(len(service.storage.list_records()), 2)
        release.set()

    def test_graceful_shutdown_marks_running_job_without_overwrite(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def runner(session_id: str, force: bool) -> dict:
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        service = self.service(
            speech_runner=runner,
            config_changes={"shutdown_wait_seconds": 0},
        )
        created = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertTrue(entered.wait(1))
        report = service.shutdown()
        failed = service.get_job(created["jobId"])
        self.assertEqual(report["runningInterrupted"], 1)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["error"]["code"], "JOB_INTERRUPTED_BY_SHUTDOWN")
        release.set()
        time.sleep(0.03)
        self.assertEqual(service.get_job(created["jobId"])["status"], "FAILED")

    def test_shutdown_interrupts_queued_job_and_rejects_new_acceptance(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def runner(session_id: str, force: bool) -> dict:
            entered.set()
            release.wait(2)
            return {"status": "ready"}

        service = self.service(
            speech_runner=runner,
            config_changes={"shutdown_wait_seconds": 0, "job_queue_capacity": 2},
        )
        running = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertTrue(entered.wait(1))
        queued = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        report = service.shutdown()
        self.assertEqual(report, {"queuedInterrupted": 1, "runningInterrupted": 1})
        self.assertEqual(service.get_job(queued["jobId"])["error"]["code"], "JOB_INTERRUPTED_BY_SHUTDOWN")
        with self.assertRaises(AnalysisApiServiceError) as raised:
            service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertEqual(raised.exception.code, "JOB_EXECUTOR_SHUTTING_DOWN")
        release.set()
        time.sleep(0.03)
        self.assertEqual(service.get_job(running["jobId"])["status"], "FAILED")

    def test_stale_lock_recovery_warning_is_persisted_on_job(self) -> None:
        service = self.service(
            speech_runner=lambda session_id, force: {"status": "ready"}
        )
        path = service.lock_manager._path("SES_000001", "SPEECH_CHARACTERISTICS")
        old = datetime.now(timezone.utc) - timedelta(minutes=2)
        write_json_atomic(path, {
            "jobId": "99999999-9999-4999-8999-999999999999",
            "sessionId": "SES_000001",
            "pipeline": "SPEECH_CHARACTERISTICS",
            "acquiredAt": old.isoformat().replace("+00:00", "Z"),
        })
        created = service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        done = wait_job(service, created["jobId"], {"SUCCEEDED_WITH_WARNINGS"})
        self.assertIn("STALE_JOB_LOCK_RECOVERED", [row["code"] for row in done["warnings"]])


class StateRecoveryAndAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_restart_recovery_fails_queued_and_running_only(self) -> None:
        storage = AnalysisJobStorage(self.root)
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        values = [
            record("11111111-1111-4111-8111-111111111111", "QUEUED", now),
            record("22222222-2222-4222-8222-222222222222", "RUNNING", now),
            record("33333333-3333-4333-8333-333333333333", "SUCCEEDED", now),
        ]
        for value in values:
            storage.create(value)
        service = AnalysisJobService(make_config(self.root), storage=storage)
        service.start()
        try:
            self.assertEqual(service.get_job(values[0]["jobId"])["error"]["code"], "JOB_INTERRUPTED_BY_RESTART")
            self.assertEqual(service.get_job(values[1]["jobId"])["error"]["code"], "JOB_INTERRUPTED_BY_RESTART")
            self.assertEqual(service.get_job(values[2]["jobId"])["status"], "SUCCEEDED")
            self.assertEqual(service.recovery_report["interruptedQueued"], 1)
            self.assertEqual(service.recovery_report["interruptedRunning"], 1)
        finally:
            service.shutdown()

    def test_invalid_terminal_transition_is_rejected(self) -> None:
        storage = AnalysisJobStorage(self.root)
        value = record(
            "44444444-4444-4444-8444-444444444444",
            "SUCCEEDED",
            datetime.now(timezone.utc),
        )
        storage.create(value)
        service = AnalysisJobService(make_config(self.root), storage=storage)
        with self.assertRaises(AnalysisApiServiceError) as raised:
            service._transition(value["jobId"], "RUNNING")
        self.assertEqual(raised.exception.code, "INVALID_JOB_STATE_TRANSITION")

    def test_readiness_does_not_create_model_and_shared_adapter_is_reused(self) -> None:
        calls = []

        def factory(profile, *, local_files_only):
            calls.append((profile, local_files_only))
            return object()

        service = AnalysisJobService(
            make_config(self.root), stt_adapter_factory=factory
        )
        service.start()
        try:
            service.readiness()
            self.assertEqual(calls, [])
            first = service._shared_adapter_factory(CPU_INT8, local_files_only=True)
            second = service._shared_adapter_factory(CPU_INT8, local_files_only=True)
            self.assertIs(first, second)
            self.assertEqual(len(calls), 1)
        finally:
            service.shutdown()

    def test_readiness_reports_bounded_executor_and_worker_warning(self) -> None:
        service = AnalysisJobService(make_config(
            self.root, job_max_workers=2, job_queue_capacity=7
        ))
        service.start()
        try:
            body, status = service.readiness()
            self.assertEqual(status, 200)
            self.assertEqual(body["status"], "READY")
            self.assertEqual(body["jobExecution"], {
                "acceptingJobs": True,
                "maxWorkers": 2,
                "activeJobs": 0,
                "queuedJobs": 0,
                "queueCapacity": 7,
            })
            self.assertEqual(body["configurationWarnings"][0]["code"], "MULTIPLE_GPU_WORKERS_CONFIGURED")
        finally:
            service.shutdown()

    def test_enabled_startup_retention_removes_only_expired_terminal(self) -> None:
        storage = AnalysisJobStorage(self.root)
        old = datetime.now(timezone.utc) - timedelta(days=40)
        value = record("55555555-5555-4555-8555-555555555555", "FAILED", old)
        storage.create(value)
        service = AnalysisJobService(
            make_config(self.root, job_retention_enabled=True), storage=storage
        )
        service.start()
        try:
            self.assertEqual(service.retention_report["deleted"], [value["jobId"]])
            self.assertEqual(storage.list_records(), [])
        finally:
            service.shutdown()


class FileLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 8, 3, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def manager(self, **changes) -> AnalysisJobLockManager:
        values = {"wait_seconds": 0, "stale_seconds": 60, "now": lambda: self.now}
        values.update(changes)
        return AnalysisJobLockManager(self.root, **values)

    def test_lock_acquire_metadata_and_release(self) -> None:
        manager = self.manager()
        acquired = manager.acquire(
            job_id="11111111-1111-4111-8111-111111111111",
            session_id="SES_000001",
            pipeline="STT_AND_SPEECH",
            job_lookup=lambda _: None,
            active_job_ids=lambda: set(),
        )
        metadata = load_json(acquired.path)
        self.assertEqual(metadata["jobId"], "11111111-1111-4111-8111-111111111111")
        self.assertTrue(manager.release(acquired, job_id=metadata["jobId"]))
        self.assertFalse(acquired.path.exists())

    def test_corrupted_lock_is_preserved_and_reported(self) -> None:
        manager = self.manager()
        path = manager._path("SES_000001", "STT_AND_SPEECH")
        path.parent.mkdir(parents=True)
        path.write_text('{"jobId": NaN}', encoding="utf-8")
        with self.assertRaises(JobLockError) as raised:
            manager.acquire(
                job_id="11111111-1111-4111-8111-111111111111",
                session_id="SES_000001",
                pipeline="STT_AND_SPEECH",
                job_lookup=lambda _: None,
                active_job_ids=lambda: set(),
            )
        self.assertEqual(raised.exception.code, "JOB_LOCK_CORRUPTED")
        self.assertTrue(path.exists())

    def test_stale_missing_owner_is_recovered_but_active_owner_is_preserved(self) -> None:
        manager = self.manager()
        path = manager._path("SES_000001", "STT_AND_SPEECH")
        old = self.now - timedelta(minutes=2)
        owner = "22222222-2222-4222-8222-222222222222"
        write_json_atomic(path, {
            "jobId": owner, "sessionId": "SES_000001", "pipeline": "STT_AND_SPEECH",
            "acquiredAt": old.isoformat().replace("+00:00", "Z"),
        })
        acquired = manager.acquire(
            job_id="33333333-3333-4333-8333-333333333333",
            session_id="SES_000001", pipeline="STT_AND_SPEECH",
            job_lookup=lambda _: None, active_job_ids=lambda: set(),
        )
        self.assertTrue(acquired.recovered_stale_lock)
        manager.release(acquired, job_id="33333333-3333-4333-8333-333333333333")

        write_json_atomic(path, {
            "jobId": owner, "sessionId": "SES_000001", "pipeline": "STT_AND_SPEECH",
            "acquiredAt": old.isoformat().replace("+00:00", "Z"),
        })
        with self.assertRaises(JobLockError) as raised:
            manager.acquire(
                job_id="44444444-4444-4444-8444-444444444444",
                session_id="SES_000001", pipeline="STT_AND_SPEECH",
                job_lookup=lambda _: None, active_job_ids=lambda: {owner},
            )
        self.assertEqual(raised.exception.code, "JOB_LOCK_TIMEOUT")
        self.assertTrue(path.exists())


def load_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


class RetentionTests(unittest.TestCase):
    def test_dry_run_and_apply_delete_only_old_unlocked_terminal_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            storage = AnalysisJobStorage(root)
            now = datetime(2026, 8, 3, tzinfo=timezone.utc)
            old = now - timedelta(days=40)
            recent = now - timedelta(days=2)
            old_delete = record("11111111-1111-4111-8111-111111111111", "FAILED", old)
            old_active = record("22222222-2222-4222-8222-222222222222", "RUNNING", old)
            old_locked = record("33333333-3333-4333-8333-333333333333", "SUCCEEDED", old)
            recent_done = record("44444444-4444-4444-8444-444444444444", "SUCCEEDED", recent)
            for value in (old_delete, old_active, old_locked, recent_done):
                storage.create(value)
            retention = AnalysisJobRetention(
                storage,
                retention_days=30,
                max_records=1000,
                lock_owner_ids=lambda: {old_locked["jobId"]},
                now=lambda: now,
            )
            dry = retention.cleanup()
            self.assertEqual(dry["mode"], "DRY_RUN")
            self.assertEqual(dry["candidates"], [old_delete["jobId"]])
            self.assertEqual(len(storage.list_records()), 4)
            applied = retention.cleanup(apply=True)
            self.assertEqual(applied["deleted"], [old_delete["jobId"]])
            remaining = {row["jobId"] for row in storage.list_records()}
            self.assertEqual(remaining, {
                old_active["jobId"], old_locked["jobId"], recent_done["jobId"]
            })


if __name__ == "__main__":
    unittest.main()
