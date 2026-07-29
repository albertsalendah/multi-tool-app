from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import Lock, Timer
from typing import Any, Callable
from uuid import uuid4

from app.execution_context import ExecutionContext
from app.job_manager import JobManager


class ScheduleStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ScheduledJob:
    id: str
    run_at: datetime
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    context: ExecutionContext | None
    timer: Timer | None = None
    job_id: str | None = None
    status: ScheduleStatus = ScheduleStatus.SCHEDULED


class Scheduler:
    """Schedules one-time executions through the platform Job Manager."""

    def __init__(self, jobs: JobManager):
        self._jobs = jobs
        self._schedules: dict[str, ScheduledJob] = {}
        self._lock = Lock()
        self._stopped = False

    def schedule(
        self,
        delay_seconds: float,
        func: Callable[..., Any],
        *args: Any,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> str:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be zero or greater.")

        with self._lock:
            if self._stopped:
                raise RuntimeError("Scheduler has been shut down.")

            schedule_id = str(uuid4())
            scheduled = ScheduledJob(
                id=schedule_id,
                run_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
                func=func,
                args=args,
                kwargs=kwargs,
                context=context,
            )
            timer = Timer(delay_seconds, self._dispatch, args=(schedule_id,))
            timer.daemon = True
            scheduled.timer = timer
            self._schedules[schedule_id] = scheduled

        timer.start()
        return schedule_id

    def _dispatch(self, schedule_id: str) -> None:
        with self._lock:
            scheduled = self._schedules.get(schedule_id)
            if scheduled is None or scheduled.status is ScheduleStatus.CANCELLED:
                return

            scheduled.job_id = self._jobs.submit(
                scheduled.func,
                *scheduled.args,
                context=scheduled.context,
                **scheduled.kwargs,
            )

    def get(self, schedule_id: str) -> ScheduledJob | None:
        with self._lock:
            return self._schedules.get(schedule_id)

    def status(self, schedule_id: str) -> ScheduleStatus | str | None:
        scheduled = self.get(schedule_id)
        if scheduled is None:
            return None

        if scheduled.job_id is None:
            return scheduled.status

        job_status = self._jobs.status(scheduled.job_id)
        return job_status.value if job_status else None

    def cancel(self, schedule_id: str) -> bool:
        with self._lock:
            scheduled = self._schedules.get(schedule_id)
            if scheduled is None or scheduled.status is ScheduleStatus.CANCELLED:
                return False

            if scheduled.job_id is None:
                scheduled.status = ScheduleStatus.CANCELLED
                if scheduled.timer:
                    scheduled.timer.cancel()
                return True

            return self._jobs.cancel(scheduled.job_id)

    def list_schedules(self) -> list[ScheduledJob]:
        with self._lock:
            return list(self._schedules.values())

    def shutdown(self) -> None:
        with self._lock:
            self._stopped = True
            for scheduled in self._schedules.values():
                if scheduled.job_id is None and scheduled.timer:
                    scheduled.status = ScheduleStatus.CANCELLED
                    scheduled.timer.cancel()
