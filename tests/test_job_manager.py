import time
from threading import Event

from app.container import ServiceContainer
from app.events import EventBus
from app.execution_context import ExecutionContext
from app.job_manager import JobManager, JobStatus


def test_report_progress_updates_job_progress_while_running():
    """Regression test: context.report_progress() used to only emit
    tool.progress - nothing updated Job.progress, so GET /jobs/{id}
    stayed at 0% until completion regardless of what a tool reported."""
    events = EventBus()
    services = ServiceContainer()
    services.register("events", events)
    manager = JobManager(event_bus=events, max_workers=1)
    context = ExecutionContext(tool_name="progress_tool", services=services)

    reported = Event()
    release = Event()

    def run():
        context.report_progress(42, "halfway")
        reported.set()
        release.wait(timeout=1)
        return "done"

    try:
        job_id = manager.submit(run, context=context)

        assert reported.wait(timeout=1)
        assert manager.get(job_id).progress == 42

        release.set()
        manager.wait(job_id, timeout=1)
        assert manager.get(job_id).progress == 100
    finally:
        manager.shutdown()


def test_tool_progress_for_untracked_job_id_is_a_safe_no_op():
    """A tool.progress event for a job_id JobManager never registered
    (e.g. a foreground ExecutionContext's own uuid) must not raise."""
    events = EventBus()
    manager = JobManager(event_bus=events, max_workers=1)

    try:
        events.emit(
            "tool.progress",
            tool="whatever",
            progress=50,
            message="",
            job_id="not-a-real-job-id",
        )
    finally:
        manager.shutdown()


def test_job_snapshot_reflects_current_fields_consistently():
    manager = JobManager(max_workers=1)

    try:
        job_id = manager.submit(lambda: "result-value")
        manager.wait(job_id, timeout=1)

        snap = manager.get(job_id).snapshot()

        assert snap.id == job_id
        assert snap.status == JobStatus.COMPLETED
        assert snap.result == "result-value"
        assert snap.error is None
        assert snap.progress == 100
    finally:
        manager.shutdown()


def test_cleanup_disabled_by_default_keeps_all_completed_jobs():
    """No completed_ttl_seconds/max_completed_jobs given -> same
    unlimited-retention behavior as before cleanup was added. This is
    also what every other JobManager()-constructing test in this suite
    relies on implicitly."""
    manager = JobManager(max_workers=1)

    try:
        ids = [manager.submit(lambda: "x") for _ in range(5)]
        for job_id in ids:
            manager.wait(job_id, timeout=1)

        assert all(manager.get(job_id) is not None for job_id in ids)
    finally:
        manager.shutdown()


def test_completed_ttl_evicts_expired_terminal_jobs_on_next_submit():
    """Pruning is opportunistic (runs at the start of submit()), so the
    expired job isn't actually gone until something submits again."""
    manager = JobManager(max_workers=1, completed_ttl_seconds=0.05)

    try:
        old_id = manager.submit(lambda: "old")
        manager.wait(old_id, timeout=1)

        time.sleep(0.1)  # past the TTL

        new_id = manager.submit(lambda: "new")
        manager.wait(new_id, timeout=1)

        assert manager.get(old_id) is None
        assert manager.get(new_id) is not None
    finally:
        manager.shutdown()


def test_max_completed_jobs_evicts_oldest_completed_first():
    manager = JobManager(max_workers=1, max_completed_jobs=2)

    try:
        ids = []
        for _ in range(3):
            job_id = manager.submit(lambda: "x")
            manager.wait(job_id, timeout=1)
            ids.append(job_id)
            time.sleep(0.01)  # distinct completed_at ordering

        # Nothing pruned yet - the 3rd submit()'s prune ran *before* the
        # 3rd job was inserted, seeing only 2 completed jobs (not over cap).
        assert manager.get(ids[0]) is not None

        # This submit() sees 3 completed jobs against a cap of 2 and
        # evicts the oldest (ids[0]) before the new job is even added.
        trigger_id = manager.submit(lambda: "trigger")
        manager.wait(trigger_id, timeout=1)

        assert manager.get(ids[0]) is None
        assert manager.get(ids[1]) is not None
        assert manager.get(ids[2]) is not None
    finally:
        manager.shutdown()


def test_running_job_is_never_evicted_by_ttl_or_count():
    manager = JobManager(max_workers=2, completed_ttl_seconds=0.01, max_completed_jobs=1)
    started = Event()
    release = Event()

    def long_running():
        started.set()
        release.wait(timeout=2)
        return "done"

    try:
        running_id = manager.submit(long_running)
        assert started.wait(timeout=1)

        time.sleep(0.05)  # past the tiny TTL, well past the tiny cap

        # Submitting and completing several other jobs (each triggering a
        # prune) must never touch the still-running job above.
        for _ in range(3):
            done_id = manager.submit(lambda: "quick")
            manager.wait(done_id, timeout=1)

        assert manager.get(running_id) is not None
        assert manager.status(running_id) == JobStatus.RUNNING

        release.set()
        manager.wait(running_id, timeout=1)
    finally:
        manager.shutdown()
