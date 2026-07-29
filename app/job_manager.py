from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future
from curses import wrapper
from enum import Enum
from threading import Lock
from uuid import uuid4


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    def __init__(self, future: Future):
        self.id = str(uuid4())
        self.future = future
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

    def submit(self, func, *args, **kwargs) -> str:
        job = Job(None)

        def wrapper():
            job.status = JobStatus.RUNNING
            if self._events:
                self._events.emit(
                    "job.started",
                    job_id=job.id,
                )
            try:
                result = func(*args, **kwargs)

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

        future = self._executor.submit(wrapper)
        job.future = future

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

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)

        if job is None:
            return False

        cancelled = job.future.cancel()

        if cancelled:
            job.status = JobStatus.CANCELLED

            if self._events:
                self._events.emit(
                    "job.cancelled",
                    job_id=job.id,
                )

        return cancelled

    def list_jobs(self):
        return list(self._jobs.values())

    def shutdown(self):
        self._executor.shutdown(wait=True)
