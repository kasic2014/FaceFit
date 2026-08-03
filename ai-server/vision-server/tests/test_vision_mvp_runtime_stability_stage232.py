from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import smoke_vision_mvp_uvicorn as smoke


class _FakeProcess:
    def __init__(self, *, wait_times_out: bool = False) -> None:
        self.returncode: int | None = None
        self.wait_times_out = wait_times_out
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float) -> int:
        self.wait_calls.append(timeout)
        if self.wait_times_out and self.kill_calls == 0:
            raise subprocess.TimeoutExpired("uvicorn", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class PortReleasePollingTests(unittest.TestCase):
    def test_immediately_released_port_succeeds_without_sleep(self) -> None:
        sleep_calls: list[float] = []

        released = smoke._wait_for_port_release(
            "127.0.0.1",
            8001,
            timeout_seconds=5.0,
            poll_interval_seconds=0.1,
            port_open=lambda _host, _port: False,
            monotonic=lambda: 0.0,
            sleep=sleep_calls.append,
        )

        self.assertTrue(released)
        self.assertEqual(sleep_calls, [])

    def test_port_released_after_short_delay_succeeds(self) -> None:
        clock = [0.0]
        states = iter((True, True, False))

        released = smoke._wait_for_port_release(
            "127.0.0.1",
            8001,
            timeout_seconds=5.0,
            poll_interval_seconds=0.1,
            port_open=lambda _host, _port: next(states),
            monotonic=lambda: clock[0],
            sleep=lambda duration: clock.__setitem__(
                0, clock[0] + duration
            ),
        )

        self.assertTrue(released)
        self.assertAlmostEqual(clock[0], 0.2)

    def test_port_remaining_open_until_timeout_fails(self) -> None:
        clock = [0.0]

        released = smoke._wait_for_port_release(
            "127.0.0.1",
            8001,
            timeout_seconds=0.3,
            poll_interval_seconds=0.1,
            port_open=lambda _host, _port: True,
            monotonic=lambda: clock[0],
            sleep=lambda duration: clock.__setitem__(
                0, clock[0] + duration
            ),
        )

        self.assertFalse(released)
        self.assertAlmostEqual(clock[0], 0.3)


class ProcessShutdownTests(unittest.TestCase):
    def test_terminate_success_stops_process(self) -> None:
        process = _FakeProcess()

        method = smoke._stop_process(
            process,
            shutdown_timeout_seconds=5.0,
        )

        self.assertEqual(method, "TERMINATED")
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 0)
        self.assertIsNotNone(process.poll())

    def test_terminate_timeout_kills_and_waits(self) -> None:
        process = _FakeProcess(wait_times_out=True)

        method = smoke._stop_process(
            process,
            shutdown_timeout_seconds=5.0,
        )

        self.assertEqual(method, "KILLED")
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 1)
        self.assertEqual(process.wait_calls, [5.0, 5.0])
        self.assertIsNotNone(process.poll())

    def test_exception_path_still_stops_spawned_process(self) -> None:
        process = _FakeProcess()
        with (
            patch.object(smoke, "_port_open", return_value=False),
            patch.object(smoke.subprocess, "Popen", return_value=process),
            patch.object(
                smoke,
                "_request",
                side_effect=RuntimeError("request failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                smoke.run_smoke(
                    vision_root=Path.cwd(),
                    host="127.0.0.1",
                    port=8001,
                    session_id="SES_000001",
                    timeout_seconds=1.0,
                )

        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 0)
        self.assertIsNotNone(process.poll())


class TestDependencyContractTests(unittest.TestCase):
    def test_starlette_testclient_dependency_is_separate(self) -> None:
        requirements = (
            Path(__file__).resolve().parents[1] / "requirements-test.txt"
        ).read_text(encoding="utf-8").splitlines()
        declarations = [
            line.strip()
            for line in requirements
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertIn("-r requirements.txt", declarations)
        self.assertIn("httpx2>=2.0.0", declarations)
        self.assertNotIn("httpx", declarations)


if __name__ == "__main__":
    unittest.main()
