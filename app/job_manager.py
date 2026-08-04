from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any
from uuid import uuid4

from app.cancellation import CancellationRequested, CancellationToken
from app.execution_context import ExecutionContext


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """An immutable, internally-consistent view of a Job's mutable
    fields, taken under Job's own lock - avoids a caller seeing e.g.
    status=COMPLETED paired with a stale/pre-update result from two
    separate unlocked attribute reads."""

    id: str
    status: JobStatus
    result: Any
    error: str | None
    progress: int


class Job:
    def __init__(
        self,
        future: Future | None,
        context: ExecutionContext | None = None,
    ):
        self.id = str(uuid4())
        self.future = future
        self.context = context
        if self.context:
            self.context.bind_job(self.id)
            self.cancellation_token = self.context.cancellation_token
        else:
            self.cancellation_token = CancellationToken()

        self._lock = Lock()
        self.status = JobStatus.PENDING
        self.result = None
        self.error = None
        self.progress = 0
        self.completed_at: float | None = None

    def _update(self, **fields):
        """Apply one or more field changes atomically. When status is
        being set to a terminal value, completed_at is stamped in the
        same locked section - JobManager's cleanup relies on completed_at
        never being set without status actually being terminal yet."""
        with self._lock:
            for key, value in fields.items():
                setattr(self, key, value)

            if fields.get("status") in _TERMINAL_STATUSES:
                self.completed_at = time.time()

    def snapshot(self) -> JobSnapshot:
        with self._lock:
            return JobSnapshot(
                id=self.id,
                status=self.status,
                result=self.result,
                error=self.error,
                progress=self.progress,
            )


class JobManager:
    def __init__(
        self,
        event_bus=None,
        max_workers: int = 4,
        completed_ttl_seconds: float | None = None,
        max_completed_jobs: int | None = None,
    ):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._events = event_bus
        # Both default to None (disabled) so a bare JobManager() - as
        # used throughout the test suite - keeps every job forever, same
        # as before this cleanup was added. The real app wires actual
        # values in from config via the Kernel.
        self._completed_ttl_seconds = completed_ttl_seconds
        self._max_completed_jobs = max_completed_jobs

        if self._events:
            # Bridges ExecutionContext.report_progress() (which only knows
            # how to emit an event) to Job.progress (which GET /jobs/{id}
            # actually reads) - same subscribe-on-the-event-bus pattern the
            # Kernel already uses for logging. Foreground executions carry
            # a job_id that was never registered in self._jobs, so
            # self._jobs.get() returns None there - safe no-op.
            self._events.subscribe("tool.progress", self._handle_tool_progress)

    def _handle_tool_progress(self, tool, progress, message, job_id):
        job = self._jobs.get(job_id)
        if job is not None:
            job._update(progress=progress)

    def _prune_completed_jobs_locked(self):
        """Caller must already hold self._lock. Drops terminal
        (completed/failed/cancelled) jobs past completed_ttl_seconds,
        then - if still over max_completed_jobs - drops the
        oldest-completed-first until back under the cap. Pending/running
        jobs are never touched by either mechanism regardless of age or
        count. Runs opportunistically from submit() rather than a
        background thread, to avoid a second always-on thread just for
        housekeeping; a bit of drift between "expired" and "actually
        removed" (until the next submit()) is an acceptable trade for
        that simplicity.
        """
        if self._completed_ttl_seconds is None and self._max_completed_jobs is None:
            return

        now = time.time()

        if self._completed_ttl_seconds is not None:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.completed_at is not None
                and now - job.completed_at >= self._completed_ttl_seconds
            ]
            for job_id in expired:
                del self._jobs[job_id]

        if self._max_completed_jobs is not None:
            completed = sorted(
                (job for job in self._jobs.values() if job.completed_at is not None),
                key=lambda job: job.completed_at,
            )
            overflow = len(completed) - self._max_completed_jobs
            for job in completed[: max(overflow, 0)]:
                del self._jobs[job.id]

    def submit(
        self,
        func,
        *args,
        context: ExecutionContext | None = None,
        **kwargs,
    ) -> str:
        job = Job(None, context=context)

        def wrapper():
            job._update(status=JobStatus.RUNNING)
            if self._events:
                self._events.emit(
                    "job.started",
                    job_id=job.id,
                )
            try:
                job.cancellation_token.raise_if_cancelled()
                result = func(*args, **kwargs)

                if job.cancellation_token.is_cancelled():
                    job._update(status=JobStatus.CANCELLED)
                    if self._events:
                        self._events.emit("job.cancelled", job_id=job.id)
                    return result

                job._update(
                    result=result,
                    progress=100,
                    status=JobStatus.COMPLETED,
                )
                if self._events:
                    self._events.emit(
                        "job.completed",
                        job_id=job.id,
                        result=result,
                    )
                return result

            except CancellationRequested as exc:
                job._update(error=str(exc), status=JobStatus.CANCELLED)
                if self._events:
                    self._events.emit("job.cancelled", job_id=job.id)
                return None

            except Exception as e:
                job._update(error=str(e), status=JobStatus.FAILED)
                if self._events:
                    self._events.emit(
                        "job.failed",
                        job_id=job.id,
                        error=str(e),
                    )
                raise

        with self._lock:
            self._prune_completed_jobs_locked()
            self._jobs[job.id] = job

        job.future = self._executor.submit(wrapper)

        return job.id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def status(self, job_id: str):
        job = self.get(job_id)
        return job.status if job else None

    def result(self, job_id: str):
        job = self.get(job_id)
        return job.result if job else None

    def context(self, job_id: str) -> ExecutionContext | None:
        job = self.get(job_id)
        return job.context if job else None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)

        if job is None or job.status in _TERMINAL_STATUSES:
            return False

        requested = job.cancellation_token.cancel()
        cancelled = job.future.cancel()

        if cancelled:
            job._update(status=JobStatus.CANCELLED)

            if self._events:
                self._events.emit(
                    "job.cancelled",
                    job_id=job.id,
                )

        return requested

    def list_jobs(self):
        return list(self._jobs.values())

    def wait(self, job_id: str, timeout=None):
        job = self.get(job_id)

        if job is None:
            return None

        return job.future.result(timeout=timeout)

    def is_finished(self, job_id: str):
        job = self.get(job_id)

        return job.future.done() if job else False

    def shutdown(self):
        self._executor.shutdown(wait=True)
