from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
from threading import Lock
from uuid import uuid4

from app.cancellation import CancellationRequested, CancellationToken
from app.execution_context import ExecutionContext


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
        self.status = JobStatus.PENDING
        self.result = None
        self.error = None
        self.progress = 0


class JobManager:
    def __init__(self, event_bus=None, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._events = event_bus

    def submit(
        self,
        func,
        *args,
        context: ExecutionContext | None = None,
        **kwargs,
    ) -> str:
        job = Job(None, context=context)

        def wrapper():
            job.status = JobStatus.RUNNING
            if self._events:
                self._events.emit(
                    "job.started",
                    job_id=job.id,
                )
            try:
                job.cancellation_token.raise_if_cancelled()
                result = func(*args, **kwargs)

                if job.cancellation_token.is_cancelled():
                    job.status = JobStatus.CANCELLED
                    if self._events:
                        self._events.emit("job.cancelled", job_id=job.id)
                    return result

                job.result = result
                job.progress = 100
                job.status = JobStatus.COMPLETED
                if self._events:
                    self._events.emit(
                        "job.completed",
                        job_id=job.id,
                        result=result,
                )
                return result

            except CancellationRequested as exc:
                job.error = str(exc)
                job.status = JobStatus.CANCELLED
                if self._events:
                    self._events.emit("job.cancelled", job_id=job.id)
                return None

            except Exception as e:
                job.error = str(e)
                job.status = JobStatus.FAILED
                if self._events:
                    self._events.emit(
                        "job.failed",
                        job_id=job.id,
                        error=str(e),
                    )
                raise

        with self._lock:
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

        if job is None or job.status in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            return False

        requested = job.cancellation_token.cancel()
        cancelled = job.future.cancel()

        if cancelled:
            job.status = JobStatus.CANCELLED

            if self._events:
                self._events.emit(
                    "job.cancelled",
                    job_id=job.id,
                )

        return requested

    def list_jobs(self):
        return list(self._jobs.values())

    def shutdown(self):
        self._executor.shutdown(wait=True)
