import os
import time

import pytest

from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool


class RecordingTool(BaseTool):
    name = "recording"

    def run(self, *, context=None, **kwargs):
        return kwargs.get("value")


class StuckTool(BaseTool):
    name = "stuck"

    def run(self, *, context=None, **kwargs):
        # Deliberately non-cooperative and self-terminating, matching
        # the JobManager-level stuck-job test - keeps this test from
        # leaking a runaway thread past its own end.
        time.sleep(0.4)
        return "finally done"


def _register(kernel: ApplicationKernel, tool: BaseTool, capabilities=None):
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": capabilities or []}
    )()


def test_tool_finished_fires_for_foreground_execution():
    kernel = ApplicationKernel()
    _register(kernel, RecordingTool())
    seen = []
    kernel.events.subscribe(
        "tool.finished", lambda tool, result: seen.append((tool, result))
    )

    kernel.run_tool("recording", value="foreground")

    assert seen == [("recording", "foreground")]


def test_tool_finished_fires_for_background_execution():
    """Regression test: tool.finished used to only be emitted on the
    synchronous path in run_tool() - background jobs never fired it."""
    kernel = ApplicationKernel()
    _register(kernel, RecordingTool())
    seen = []
    kernel.events.subscribe(
        "tool.finished", lambda tool, result: seen.append((tool, result))
    )

    job_id = kernel.run_tool("recording", background=True, value="background")

    try:
        kernel.jobs.wait(job_id, timeout=1)
    finally:
        kernel.jobs.shutdown()

    assert seen == [("recording", "background")]


def test_kernel_shutdown_respects_configured_timeout_for_a_stuck_background_job():
    """Confirms jobs.shutdown_timeout_seconds is actually wired through
    Kernel -> Config -> JobManager.shutdown(), not just implemented and
    left unused. Uses an env var override (exercising the Config
    coercion fix too) to keep the test fast rather than waiting out the
    real 10s default."""
    old = os.environ.get("JOBS_SHUTDOWN_TIMEOUT_SECONDS")
    os.environ["JOBS_SHUTDOWN_TIMEOUT_SECONDS"] = "0.05"
    try:
        kernel = ApplicationKernel()
        _register(kernel, StuckTool())
        kernel._initialized = True  # skip real initialize(): its
        # discover_tools() clears and re-scans the registry, which would
        # wipe out the manually-registered StuckTool above. shutdown()
        # only needs the flag itself, not a full real initialize().

        kernel.run_tool("stuck", background=True)

        start = time.time()
        kernel.shutdown()
        elapsed = time.time() - start

        assert elapsed < 0.4  # gave up well before the tool's own 0.4s finishes
    finally:
        if old is None:
            os.environ.pop("JOBS_SHUTDOWN_TIMEOUT_SECONDS", None)
        else:
            os.environ["JOBS_SHUTDOWN_TIMEOUT_SECONDS"] = old


def test_schedule_tool_validates_unknown_tool_immediately():
    """Regression guard: schedule_tool() must fail right away for a bad
    tool name, not silently succeed and only surface as a failed job
    once the timer eventually fires."""
    kernel = ApplicationKernel()

    with pytest.raises(KeyError):
        kernel.schedule_tool(10, "does_not_exist")

    kernel.scheduler.shutdown()
    kernel.jobs.shutdown()


def test_schedule_tool_validates_missing_capability_immediately():
    kernel = ApplicationKernel()
    _register(kernel, RecordingTool(), capabilities=["browser"])
    # No "browser" service registered (kernel.initialize() never ran),
    # so this must fail immediately, same as run_tool() would.

    with pytest.raises(RuntimeError):
        kernel.schedule_tool(10, "recording", value="x")

    kernel.scheduler.shutdown()
    kernel.jobs.shutdown()


def test_schedule_tool_runs_the_real_tool_after_the_delay():
    """The one JobManager job a schedule dispatches into must be the
    actual tool execution (real result), not a throwaway job whose
    result is just another job_id."""
    kernel = ApplicationKernel()
    _register(kernel, RecordingTool())

    try:
        schedule_id = kernel.schedule_tool(0.01, "recording", value="scheduled")

        deadline = time.time() + 1
        job_id = None
        while job_id is None and time.time() < deadline:
            scheduled = kernel.scheduler.get(schedule_id)
            job_id = scheduled.job_id if scheduled else None
            time.sleep(0.01)

        assert job_id is not None
        result = kernel.jobs.wait(job_id, timeout=1)

        assert result == "scheduled"
        assert kernel.scheduler.status(schedule_id) == "completed"
    finally:
        kernel.scheduler.shutdown()
        kernel.jobs.shutdown()
