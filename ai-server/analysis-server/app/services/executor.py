"""Bounded model execution without HTTP-client-style retries."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.services.analysis_contracts import AnalyzerTimeout


T = TypeVar("T")


class AnalysisExecutor:
    def __init__(self, max_workers: int = 1) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="facefit-analysis",
        )

    async def run(
        self,
        function: Callable[[], T],
        *,
        timeout_seconds: float,
        cleanup: Callable[[], None],
    ) -> T:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._pool, function)
        try:
            value = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=timeout_seconds,
            )
        # Python 3.10 keeps asyncio.TimeoutError separate from the built-in
        # TimeoutError; Python 3.11+ aliases them. Support the declared 3.10
        # container runtime and newer local runtimes with the same contract.
        except (asyncio.TimeoutError, TimeoutError) as exc:
            future.add_done_callback(lambda _completed: cleanup())
            raise AnalyzerTimeout from exc
        except asyncio.CancelledError:
            future.add_done_callback(lambda _completed: cleanup())
            raise
        except Exception:
            cleanup()
            raise
        cleanup()
        return value

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
