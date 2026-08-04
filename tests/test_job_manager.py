from threading import Event

from app.container import ServiceContainer
from app.events import EventBus
from app.execution_context import ExecutionContext
from app.job_manager import JobManager


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
