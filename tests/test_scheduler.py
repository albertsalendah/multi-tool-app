import time
from threading import Event

from app.events import EventBus
from app.job_manager import JobManager
from app.scheduler import ScheduleStatus, Scheduler


def _dispatched_job_id(scheduler, schedule_id, timeout=1):
    """Poll until a schedule's Timer has fired and it has a job_id -
    dispatch itself happens asynchronously via threading.Timer."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        scheduled = scheduler.get(schedule_id)
        if scheduled is not None and scheduled.job_id is not None:
            return scheduled.job_id
        time.sleep(0.01)
    raise AssertionError(f"schedule {schedule_id} never dispatched within {timeout}s")


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


def test_cleanup_disabled_by_default_keeps_everything():
    """No completed_ttl_seconds/max_completed_schedules given -> same
    unlimited-retention behavior as before cleanup was added."""
    jobs = JobManager(max_workers=1)
    scheduler = Scheduler(jobs)

    try:
        ids = []
        for _ in range(5):
            sid = scheduler.schedule(10, lambda: None)
            scheduler.cancel(sid)
            ids.append(sid)

        assert all(scheduler.get(sid) is not None for sid in ids)
    finally:
        scheduler.shutdown()
        jobs.shutdown()


def test_cancelled_before_dispatch_schedule_is_ttl_pruned_on_next_schedule():
    jobs = JobManager(max_workers=1)
    scheduler = Scheduler(jobs, completed_ttl_seconds=0.05)

    try:
        old_id = scheduler.schedule(10, lambda: None)
        assert scheduler.cancel(old_id)

        time.sleep(0.1)  # past the TTL

        # Pruning is opportunistic (runs at the start of schedule()), so
        # old_id isn't actually gone until something schedules again.
        new_id = scheduler.schedule(10, lambda: None)
        scheduler.cancel(new_id)

        assert scheduler.get(old_id) is None
        assert scheduler.get(new_id) is not None
    finally:
        scheduler.shutdown()
        jobs.shutdown()


def test_dispatched_and_completed_schedule_is_ttl_pruned_on_next_schedule():
    events = EventBus()
    jobs = JobManager(event_bus=events, max_workers=1)
    scheduler = Scheduler(jobs, event_bus=events, completed_ttl_seconds=0.05)

    try:
        old_id = scheduler.schedule(0.01, lambda: "done")

        job_id = _dispatched_job_id(scheduler, old_id)
        # jobs.wait() blocks until JobManager's wrapper() - including its
        # job.completed emit(), which Scheduler's own subscriber reacts
        # to - is entirely done, so there's no race on completed_at.
        jobs.wait(job_id, timeout=1)
        assert scheduler.get(old_id).completed_at is not None

        time.sleep(0.1)  # past the TTL

        new_id = scheduler.schedule(10, lambda: None)
        scheduler.cancel(new_id)

        assert scheduler.get(old_id) is None
    finally:
        scheduler.shutdown()
        jobs.shutdown()


def test_max_completed_schedules_evicts_oldest_completed_first():
    jobs = JobManager(max_workers=1)
    scheduler = Scheduler(jobs, max_completed_schedules=2)

    try:
        ids = []
        for _ in range(3):
            sid = scheduler.schedule(10, lambda: None)
            scheduler.cancel(sid)
            ids.append(sid)
            time.sleep(0.01)  # distinct completed_at ordering

        # Nothing pruned yet - no schedule() has run since the 3rd
        # cancel(), and pruning only happens at the start of schedule().
        assert scheduler.get(ids[0]) is not None

        trigger_id = scheduler.schedule(10, lambda: None)
        scheduler.cancel(trigger_id)

        assert scheduler.get(ids[0]) is None
        assert scheduler.get(ids[1]) is not None
        assert scheduler.get(ids[2]) is not None
    finally:
        scheduler.shutdown()
        jobs.shutdown()


def test_pending_and_running_schedules_are_never_evicted():
    events = EventBus()
    jobs = JobManager(event_bus=events, max_workers=2)
    scheduler = Scheduler(
        jobs, event_bus=events, completed_ttl_seconds=0.01, max_completed_schedules=1
    )
    started = Event()
    release = Event()

    def long_running():
        started.set()
        release.wait(timeout=2)
        return "done"

    try:
        running_id = scheduler.schedule(0.01, long_running)
        assert started.wait(timeout=1)

        pending_id = scheduler.schedule(10, lambda: None)  # never fires here

        time.sleep(0.05)  # past the tiny TTL, well past the tiny cap

        # Several quick schedule()->cancel() round trips, each a prune
        # opportunity - must never touch the still-running or
        # still-pending schedules above.
        for _ in range(3):
            sid = scheduler.schedule(10, lambda: None)
            scheduler.cancel(sid)

        assert scheduler.get(running_id) is not None
        assert scheduler.get(pending_id) is not None
        assert scheduler.status(pending_id) == ScheduleStatus.SCHEDULED

        release.set()
        running_job_id = scheduler.get(running_id).job_id
        jobs.wait(running_job_id, timeout=1)
        scheduler.cancel(pending_id)
    finally:
        scheduler.shutdown()
        jobs.shutdown()
