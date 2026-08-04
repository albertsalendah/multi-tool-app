from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool


class RecordingTool(BaseTool):
    name = "recording"

    def run(self, *, context=None, **kwargs):
        return kwargs.get("value")


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
