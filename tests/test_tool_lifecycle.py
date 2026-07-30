from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool, ToolValidationError


class LifecycleTrackingTool(BaseTool):
    name = "lifecycle_tracker"

    def __init__(self):
        self.calls = []

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
    name = "raising_tool"

    def __init__(self):
        self.cleanup_called = False

    def run(self, *, context=None, **kwargs):
        raise RuntimeError("run failed")

    def cleanup(self, context=None):
        self.cleanup_called = True


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
    tool = LifecycleTrackingTool()
    kernel = _kernel_with(tool)

    result = kernel.run_tool("lifecycle_tracker", value=42)

    assert result == 42
    assert [c[0] for c in tool.calls] == ["initialize", "validate", "run", "cleanup"]
    # context is threaded into both initialize() and cleanup()
    assert tool.calls[0][1] == "lifecycle_tracker"
    assert tool.calls[3][1] == "lifecycle_tracker"


def test_validate_rejection_raises_and_skips_run_but_still_cleans_up():
    tool = LifecycleTrackingTool()
    kernel = _kernel_with(tool)

    try:
        kernel.run_tool("lifecycle_tracker", value=1, should_validate=False)
    except ToolValidationError:
        pass
    else:
        raise AssertionError("Expected ToolValidationError.")

    assert [c[0] for c in tool.calls] == ["initialize", "validate", "cleanup"]


def test_cleanup_runs_even_when_run_raises():
    tool = RaisingTool()
    kernel = _kernel_with(tool)

    try:
        kernel.run_tool("raising_tool")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError to propagate.")

    assert tool.cleanup_called is True


def test_background_execution_also_runs_the_full_lifecycle():
    tool = LifecycleTrackingTool()
    kernel = _kernel_with(tool)

    try:
        job_id = kernel.run_tool("lifecycle_tracker", background=True, value="bg")
        result = kernel.jobs.wait(job_id, timeout=1)
    finally:
        kernel.jobs.shutdown()

    assert result == "bg"
    assert [c[0] for c in tool.calls] == ["initialize", "validate", "run", "cleanup"]


def test_default_lifecycle_hooks_are_noop_for_tools_that_dont_override_them():
    kernel = _kernel_with(MinimalTool())

    assert kernel.run_tool("minimal") == "ok"
