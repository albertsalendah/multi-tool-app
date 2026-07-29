from threading import Event

from app.job_manager import JobManager
from app.scheduler import ScheduleStatus, Scheduler


def test_scheduler_dispatches_work_through_the_job_manager():
    jobs = JobManager(max_workers=1)
    scheduler = Scheduler(jobs)
    completed = Event()

    try:
        schedule_id = scheduler.schedule(0.01, lambda: completed.set())

        assert scheduler.status(schedule_id) == ScheduleStatus.SCHEDULED
        assert completed.wait(timeout=1)

        scheduled = scheduler.get(schedule_id)
        assert scheduled is not None
        assert scheduled.job_id is not None
        assert jobs.get(scheduled.job_id).future.result(timeout=1) is None
        assert scheduler.status(schedule_id) == "completed"
    finally:
        scheduler.shutdown()
        jobs.shutdown()


def test_scheduler_cancels_work_before_dispatch():
    jobs = JobManager(max_workers=1)
    scheduler = Scheduler(jobs)
    executed = Event()

    try:
        schedule_id = scheduler.schedule(1, executed.set)

        assert scheduler.cancel(schedule_id)
        assert scheduler.status(schedule_id) == ScheduleStatus.CANCELLED
        assert not executed.wait(timeout=0.05)
        assert not scheduler.cancel(schedule_id)
    finally:
        scheduler.shutdown()
        jobs.shutdown()
