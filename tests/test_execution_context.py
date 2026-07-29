import time
from threading import Event

from app.container import ServiceContainer
from app.cancellation import CancellationRequested, CancellationToken
from app.execution_context import ExecutionContext
from app.job_manager import JobManager
from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool


class ContextTool(BaseTool):
    name = "context_tool"

    def run(self, *, context=None, **kwargs):
        context.set_state("handled", True)
        return {
            "job_id": context.job_id,
            "tool_name": context.tool_name,
            "request": dict(context.request),
            "handled": context.get_state("handled"),
            "services_match": context.get_service("marker") is kwargs["services"].get("marker"),
        }


def test_context_keeps_request_read_only_and_state_isolated():
    services = ServiceContainer()
    first = ExecutionContext(tool_name="first", services=services, request={"value": 1})
    second = ExecutionContext(tool_name="second", services=services)

    first.set_state("value", 1)

    assert dict(first.request) == {"value": 1}
    assert first.get_state("value") == 1
    assert second.get_state("value") is None


def test_job_manager_binds_context_to_job():
    services = ServiceContainer()
    context = ExecutionContext(tool_name="example", services=services)
    manager = JobManager(max_workers=1)

    try:
        job_id = manager.submit(lambda: "done", context=context)
        assert context.job_id == job_id
        assert manager.context(job_id) is context
        assert manager.get(job_id).future.result(timeout=1) == "done"
    finally:
        manager.shutdown()


def test_kernel_passes_context_for_foreground_and_background_execution():
    kernel = ApplicationKernel()
    marker = object()
    kernel.container.register("marker", marker)
    kernel.registry.register(ContextTool())
    kernel.registry._manifests["context_tool"] = type(
        "Manifest", (), {"capabilities": []}
    )()

    foreground = kernel.run_tool("context_tool", value="foreground")
    job_id = kernel.run_tool("context_tool", background=True, value="background")

    try:
        background = kernel.jobs.get(job_id).future.result(timeout=1)
    finally:
        kernel.jobs.shutdown()

    assert foreground["tool_name"] == "context_tool"
    assert foreground["request"]["value"] == "foreground"
    assert foreground["services_match"]
    assert background["job_id"] == job_id
    assert background["request"]["value"] == "background"
    assert background["services_match"]


def test_cancellation_token_signals_and_raises():
    token = CancellationToken()

    assert token.cancel()
    assert token.is_cancelled()
    assert not token.cancel()

    try:
        token.raise_if_cancelled()
    except CancellationRequested:
        pass
    else:
        raise AssertionError("Expected cancellation to raise.")


def test_job_manager_cancels_a_cooperative_running_job():
    services = ServiceContainer()
    context = ExecutionContext(tool_name="example", services=services)
    manager = JobManager(max_workers=1)
    started = Event()

    def run_until_cancelled():
        started.set()
        while True:
            context.raise_if_cancelled()
            time.sleep(0.001)

    try:
        job_id = manager.submit(run_until_cancelled, context=context)
        assert started.wait(timeout=1)
        assert manager.cancel(job_id)
        assert manager.get(job_id).future.result(timeout=1) is None
        assert manager.status(job_id).value == "cancelled"
    finally:
        manager.shutdown()
