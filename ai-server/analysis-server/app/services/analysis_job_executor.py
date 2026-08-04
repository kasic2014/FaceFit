"""Bounded in-process worker queue for Analysis API jobs."""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable


class JobExecutorError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_STOP = object()


class AnalysisJobExecutor:
    def __init__(
        self,
        *,
        max_workers: int,
        queue_capacity: int,
        handler: Callable[[str], None],
        interrupt_handler: Callable[[str, str], None],
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_workers = max_workers
        self.queue_capacity = queue_capacity
        self._handler = handler
        self._interrupt_handler = interrupt_handler
        self._monotonic = monotonic
        self._queue: queue.Queue[str | object] = queue.Queue()
        self._slots = threading.BoundedSemaphore(queue_capacity)
        self._condition = threading.Condition(threading.RLock())
        self._active: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._accepting = False
        self._shutdown = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            if self._shutdown:
                raise JobExecutorError(
                    "JOB_EXECUTOR_SHUTTING_DOWN", "Analysis job executor is stopped"
                )
            self._started = True
            self._accepting = True
            for index in range(self.max_workers):
                thread = threading.Thread(
                    target=self._worker,
                    name=f"analysis-job-worker-{index + 1}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def reserve(self) -> bool:
        with self._condition:
            if not self._started or not self._accepting or self._shutdown:
                return False
        return self._slots.acquire(blocking=False)

    def enqueue_reserved(self, job_id: str) -> None:
        with self._condition:
            if not self._accepting or self._shutdown:
                self._slots.release()
                raise JobExecutorError(
                    "JOB_EXECUTOR_SHUTTING_DOWN", "Analysis job executor is shutting down"
                )
            self._queue.put_nowait(job_id)
            self._condition.notify_all()

    def cancel_reservation(self) -> None:
        self._slots.release()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                return
            job_id = str(item)
            self._slots.release()
            with self._condition:
                self._active.add(job_id)
                self._condition.notify_all()
            try:
                try:
                    self._handler(job_id)
                except Exception:
                    # A worker must survive a single malformed or failed job. The service
                    # handler is responsible for persisting a safe FAILED state.
                    pass
            finally:
                with self._condition:
                    self._active.discard(job_id)
                    self._condition.notify_all()
                self._queue.task_done()

    def active_job_ids(self) -> set[str]:
        with self._condition:
            return set(self._active)

    def metrics(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "acceptingJobs": self._accepting and not self._shutdown,
                "maxWorkers": self.max_workers,
                "activeJobs": len(self._active),
                "queuedJobs": self._queue.qsize(),
                "queueCapacity": self.queue_capacity,
            }

    def shutdown(self, wait_seconds: float) -> dict[str, int]:
        with self._condition:
            if self._shutdown:
                return {"queuedInterrupted": 0, "runningInterrupted": 0}
            self._accepting = False
            deadline = self._monotonic() + wait_seconds
            while (self._active or not self._queue.empty()) and self._monotonic() < deadline:
                self._condition.wait(timeout=max(0.0, deadline - self._monotonic()))

            queued: list[str] = []
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not _STOP:
                    queued.append(str(item))
                    self._slots.release()
                self._queue.task_done()
            active = list(self._active)
            self._shutdown = True
            for _ in self._threads:
                self._queue.put_nowait(_STOP)
            self._condition.notify_all()

        for job_id in queued:
            self._interrupt_handler(job_id, "JOB_INTERRUPTED_BY_SHUTDOWN")
        for job_id in active:
            self._interrupt_handler(job_id, "JOB_INTERRUPTED_BY_SHUTDOWN")
        remaining = max(0.0, deadline - self._monotonic())
        for thread in self._threads:
            thread.join(timeout=remaining)
            remaining = max(0.0, deadline - self._monotonic())
        return {
            "queuedInterrupted": len(queued),
            "runningInterrupted": len(active),
        }
