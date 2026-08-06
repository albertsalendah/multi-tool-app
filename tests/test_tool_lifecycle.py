from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool, ToolValidationError


class LifecycleTrackingTool(BaseTool):
    """calls is deliberately a class-level list, not set in __init__.

    kernel.run_tool() now runs a fresh instance per execution (see
    ToolRegistry.create_tool_instance()), so an instance-level list set
    in __init__ would never be visible to whichever LifecycleTrackingTool()
    the test itself constructed for registration - only to the separate
    instance that actually ran. A class-level list is shared by every
    instance of the class regardless of which one executed, so it stays
    a reliable way to observe lifecycle order across the instantiation
    change. Reset explicitly at the start of each test that uses it, to
    avoid leaking calls between tests.
    """

    name = "lifecycle_tracker"
    calls: list = []

    def initialize(self, context=None):
        self.calls.append(("initialize", context.tool_name if context else None))

    def validate(self, request):
        self.calls.append(("validate", dict(request)))
        return request.get("should_validate", True)

    def run(self, *, context=None, **kwargs):
        self.calls.append(("run", kwargs.get("value")))
        return kwargs.get("value")

    def cleanup(self, context=None):
        self.calls.append(("cleanup", context.tool_name if context else None))


class RaisingTool(BaseTool):
    """cleanup_called is a class-level bool, and cleanup() assigns it via
    the class name (RaisingTool.cleanup_called = True), not self.cleanup_called
    = True - the latter would create an instance-level shadow attribute
    invisible to the test's own reference, since bool assignment (unlike
    mutating a list in place) always creates a new binding. Same
    fresh-instance-per-execution reasoning as LifecycleTrackingTool above.
    """

    name = "raising_tool"
    cleanup_called = False

    def run(self, *, context=None, **kwargs):
        raise RuntimeError("run failed")

    def cleanup(self, context=None):
        RaisingTool.cleanup_called = True


class MinimalTool(BaseTool):
    """A tool that overrides nothing but the required run() - exercises
    the no-op defaults."""

    name = "minimal"

    def run(self, *, context=None, **kwargs):
        return "ok"


def _kernel_with(tool: BaseTool) -> ApplicationKernel:
    kernel = ApplicationKernel()
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": []}
    )()
    return kernel


def test_lifecycle_runs_in_order_for_foreground_execution():
    LifecycleTrackingTool.calls = []
    kernel = _kernel_with(LifecycleTrackingTool())

    result = kernel.run_tool("lifecycle_tracker", value=42)

    assert result == 42
    calls = LifecycleTrackingTool.calls
    assert [c[0] for c in calls] == ["initialize", "validate", "run", "cleanup"]
    # context is threaded into both initialize() and cleanup()
    assert calls[0][1] == "lifecycle_tracker"
    assert calls[3][1] == "lifecycle_tracker"


def test_validate_rejection_raises_and_skips_run_but_still_cleans_up():
    LifecycleTrackingTool.calls = []
    kernel = _kernel_with(LifecycleTrackingTool())

    try:
        kernel.run_tool("lifecycle_tracker", value=1, should_validate=False)
    except ToolValidationError:
        pass
    else:
        raise AssertionError("Expected ToolValidationError.")

    assert [c[0] for c in LifecycleTrackingTool.calls] == [
        "initialize", "validate", "cleanup"
    ]


def test_cleanup_runs_even_when_run_raises():
    RaisingTool.cleanup_called = False
    kernel = _kernel_with(RaisingTool())

    try:
        kernel.run_tool("raising_tool")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError to propagate.")

    assert RaisingTool.cleanup_called is True


def test_background_execution_also_runs_the_full_lifecycle():
    LifecycleTrackingTool.calls = []
    kernel = _kernel_with(LifecycleTrackingTool())

    try:
        job_id = kernel.run_tool("lifecycle_tracker", background=True, value="bg")
        result = kernel.jobs.wait(job_id, timeout=1)
    finally:
        kernel.jobs.shutdown()

    assert result == "bg"
    assert [c[0] for c in LifecycleTrackingTool.calls] == [
        "initialize", "validate", "run", "cleanup"
    ]


def test_default_lifecycle_hooks_are_noop_for_tools_that_dont_override_them():
    kernel = _kernel_with(MinimalTool())

    assert kernel.run_tool("minimal") == "ok"
