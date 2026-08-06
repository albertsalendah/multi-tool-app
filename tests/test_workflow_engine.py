import time

from app.kernel import ApplicationKernel
from app.workflow import ParallelGroup, Workflow, WorkflowStep
from app.workflow_engine import WorkflowGroupError
from tools.base_tool import BaseTool


# --------------------------------------------------------------------------
# Test tools
# --------------------------------------------------------------------------


class EchoTool(BaseTool):
    name = "echo"

    def run(self, *, context=None, **kwargs):
        return kwargs.get("value")


class SleepTool(BaseTool):
    name = "sleep"

    def run(self, *, context=None, **kwargs):
        seconds = kwargs.get("seconds", 0)
        time.sleep(seconds)
        return seconds


class FlakyTool(BaseTool):
    """Fails `fail_times` calls, then succeeds. calls is deliberately a
    class-level counter, not per-instance: kernel.run_tool() creates a
    fresh tool instance for every attempt including retries (see
    ToolRegistry.create_tool_instance()), so per-instance state would
    reset to 0 on every retry and this could never recover. A
    class-level counter simulates a flaky *external* resource - the
    realistic case retries actually exist to handle - rather than the
    tool object itself remembering its own attempt count, which isn't
    how a real transient failure would behave anyway."""

    name = "flaky"
    calls = 0

    def run(self, *, context=None, **kwargs):
        FlakyTool.calls += 1
        fail_times = kwargs.get("fail_times", 0)

        if FlakyTool.calls <= fail_times:
            raise RuntimeError(f"transient failure #{FlakyTool.calls}")

        return FlakyTool.calls


class AlwaysFailTool(BaseTool):
    name = "always_fail"

    def run(self, *, context=None, **kwargs):
        raise RuntimeError("boom")


def _register(kernel: ApplicationKernel, tool: BaseTool):
    """Register a tool with a permissive manifest, bypassing plugin
    discovery. Same pattern as tests/test_execution_context.py."""
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": []}
    )()


def _kernel_with_tools(*tools) -> ApplicationKernel:
    kernel = ApplicationKernel()
    for tool in tools:
        _register(kernel, tool)
    return kernel


class _EventCollector:
    """Subscribes to every workflow.* event and records (name, payload)
    in emission order, so tests can assert on the full event timeline."""

    EVENTS = ("workflow.started", "workflow.progress", "workflow.completed", "workflow.failed")

    def __init__(self, kernel: ApplicationKernel):
        self.records: list[tuple[str, dict]] = []

        for event in self.EVENTS:
            # default arg binds `event` per-iteration instead of by
            # closure reference (classic late-binding lambda pitfall).
            kernel.events.subscribe(
                event,
                lambda event=event, **payload: self.records.append((event, payload)),
            )

    def names(self) -> list[str]:
        return [name for name, _ in self.records]

    def payloads(self, event: str) -> list[dict]:
        return [payload for name, payload in self.records if name == event]


# --------------------------------------------------------------------------
# Linear execution: state wiring, variable substitution, conditions
# --------------------------------------------------------------------------


def test_sequential_steps_resolve_variables_through_workflow_state():
    kernel = _kernel_with_tools(EchoTool())
    wf = Workflow("linear")

    wf.add_step("echo", value=5, result_as="a")
    wf.add_step("echo", value="got:{{a}}", result_as="b")

    results = kernel.workflow.execute(wf)

    assert results == [5, "got:5"]
    assert wf.state.get("a") == 5
    assert wf.state.get("b") == "got:5"


def test_condition_skips_step_without_running_it():
    kernel = _kernel_with_tools(EchoTool())
    wf = Workflow("conditional")

    wf.add_step("echo", value=1, result_as="skip_me", condition="1 > 2")
    wf.add_step("echo", value=2, result_as="keep_me", condition="1 < 2")

    results = kernel.workflow.execute(wf)

    assert results == [2]
    assert wf.state.has("skip_me") is False
    assert wf.state.get("keep_me") == 2


def test_condition_can_reference_earlier_step_results():
    kernel = _kernel_with_tools(EchoTool())
    wf = Workflow("conditional-on-state")

    wf.add_step("echo", value=10, result_as="a")
    wf.add_step("echo", value="ran", result_as="b", condition="a == 10")

    results = kernel.workflow.execute(wf)

    assert results == [10, "ran"]


# --------------------------------------------------------------------------
# Retry / continue_on_error
# --------------------------------------------------------------------------


def test_retry_recovers_from_transient_failure():
    FlakyTool.calls = 0
    kernel = _kernel_with_tools(FlakyTool())
    wf = Workflow("retry")

    wf.add_step("flaky", fail_times=2, retry=2, result_as="result")

    results = kernel.workflow.execute(wf)

    assert results == [3]
    assert FlakyTool.calls == 3


def test_step_failure_propagates_without_continue_on_error():
    kernel = _kernel_with_tools(AlwaysFailTool())
    wf = Workflow("hard-failure")

    wf.add_step("always_fail")

    try:
        kernel.workflow.execute(wf)
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("Expected the step failure to propagate.")


def test_continue_on_error_swallows_failure_and_keeps_going():
    kernel = _kernel_with_tools(AlwaysFailTool(), EchoTool())
    wf = Workflow("soft-failure")

    wf.add_step("always_fail", continue_on_error=True)
    wf.add_step("echo", value="still ran", result_as="after")

    results = kernel.workflow.execute(wf)

    assert results == ["still ran"]
    assert wf.state.get("after") == "still ran"


def test_timeout_raises_timeout_error():
    kernel = _kernel_with_tools(SleepTool())
    wf = Workflow("timeout")

    wf.add_step("sleep", seconds=0.15, timeout=0.02)

    try:
        kernel.workflow.execute(wf)
    except Exception as exc:
        assert "TimeoutError" in type(exc).__name__ or isinstance(
            exc, TimeoutError
        )
    else:
        raise AssertionError("Expected a timeout error.")


# --------------------------------------------------------------------------
# ParallelGroup: concurrency + run-to-completion failure aggregation
# --------------------------------------------------------------------------


def test_parallel_group_runs_branches_concurrently():
    kernel = _kernel_with_tools(SleepTool())
    wf = Workflow("parallel-timing")

    with wf.parallel():
        wf.add_step("sleep", seconds=0.15, result_as="first")
        wf.add_step("sleep", seconds=0.15, result_as="second")

    start = time.perf_counter()
    results = kernel.workflow.execute(wf)
    elapsed = time.perf_counter() - start

    # Sequential execution would take >= 0.30s; concurrent should be well
    # under that even with scheduling overhead.
    assert elapsed < 0.28, f"branches did not run concurrently ({elapsed:.3f}s)"
    assert results == [0.15, 0.15]
    assert wf.state.get("first") == 0.15
    assert wf.state.get("second") == 0.15


def test_parallel_group_preserves_branch_order_in_flattened_results():
    kernel = _kernel_with_tools(EchoTool())
    wf = Workflow("parallel-order")

    with wf.parallel():
        wf.add_step("echo", value="a")
        wf.add_step("echo", value="b")
        wf.add_step("echo", value="c")

    results = kernel.workflow.execute(wf)

    assert results == ["a", "b", "c"]


def test_parallel_group_runs_every_branch_to_completion_before_raising():
    echo = EchoTool()
    kernel = _kernel_with_tools(echo, AlwaysFailTool())
    wf = Workflow("parallel-partial-failure")

    with wf.parallel():
        wf.add_step("echo", value="ok-1", result_as="ok_1")
        wf.add_step("always_fail")
        wf.add_step("echo", value="ok-2", result_as="ok_2")

    try:
        kernel.workflow.execute(wf)
    except WorkflowGroupError as exc:
        assert len(exc.failures) == 1
        failing_node, error = exc.failures[0]
        assert isinstance(failing_node, WorkflowStep)
        assert failing_node.tool == "always_fail"
    else:
        raise AssertionError("Expected WorkflowGroupError.")

    # The two successful sibling branches still completed and wrote their
    # results into shared state, proving the group ran to completion
    # instead of cancelling on the first failure.
    assert wf.state.get("ok_1") == "ok-1"
    assert wf.state.get("ok_2") == "ok-2"


def test_nested_parallel_group_is_flattened_by_the_engine():
    kernel = _kernel_with_tools(EchoTool())
    wf = Workflow("nested-parallel")

    # Workflow.parallel() itself refuses to nest via the fluent API, so we
    # build the nested structure directly to confirm the engine's node
    # dispatch is recursive.
    inner = ParallelGroup()
    inner.add(WorkflowStep(tool="echo", params={"value": "inner-1"}))
    inner.add(WorkflowStep(tool="echo", params={"value": "inner-2"}))

    outer = ParallelGroup()
    outer.add(WorkflowStep(tool="echo", params={"value": "outer-1"}))
    outer.add(inner)

    wf.nodes.append(outer)

    results = kernel.workflow.execute(wf)

    assert sorted(results) == ["inner-1", "inner-2", "outer-1"]


# --------------------------------------------------------------------------
# Workflow Events: started / progress / completed / failed
# --------------------------------------------------------------------------


def test_successful_workflow_emits_started_progress_and_completed():
    kernel = _kernel_with_tools(EchoTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-success")

    wf.add_step("echo", value="a", result_as="a")
    wf.add_step("echo", value="b", result_as="b")

    kernel.workflow.execute(wf)

    # started, progress, progress, completed - in that order.
    assert collector.names() == [
        "workflow.started",
        "workflow.progress",
        "workflow.progress",
        "workflow.completed",
    ]

    started = collector.payloads("workflow.started")[0]
    assert started["workflow"] == "events-success"
    assert started["total_steps"] == 2
    assert started["background"] is False

    progress = collector.payloads("workflow.progress")
    assert [p["completed"] for p in progress] == [1, 2]
    assert [p["total"] for p in progress] == [2, 2]
    assert [p["percent"] for p in progress] == [50, 100]
    assert [p["status"] for p in progress] == ["succeeded", "succeeded"]
    assert [p["tool"] for p in progress] == ["echo", "echo"]

    completed = collector.payloads("workflow.completed")[0]
    assert completed["workflow"] == "events-success"
    assert completed["result_count"] == 2
    assert completed["duration"] >= 0

    # No workflow.failed should ever fire on a clean run.
    assert "workflow.failed" not in collector.names()


def test_all_four_events_share_the_same_execution_id():
    kernel = _kernel_with_tools(EchoTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-correlation")

    wf.add_step("echo", value=1)

    kernel.workflow.execute(wf)

    execution_ids = {payload["execution_id"] for _, payload in collector.records}
    assert len(execution_ids) == 1


def test_two_executions_of_the_same_workflow_get_different_execution_ids():
    kernel = _kernel_with_tools(EchoTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-rerun")

    wf.add_step("echo", value=1)

    kernel.workflow.execute(wf)
    kernel.workflow.execute(wf)

    started = collector.payloads("workflow.started")
    assert len(started) == 2
    assert started[0]["execution_id"] != started[1]["execution_id"]


def test_condition_skip_reports_skipped_progress_status():
    kernel = _kernel_with_tools(EchoTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-skip")

    wf.add_step("echo", value=1, condition="1 > 2")

    kernel.workflow.execute(wf)

    progress = collector.payloads("workflow.progress")
    assert len(progress) == 1
    assert progress[0]["status"] == "skipped"
    assert progress[0]["completed"] == 1
    assert progress[0]["total"] == 1


def test_continue_on_error_reports_failed_ignored_status_and_still_completes():
    kernel = _kernel_with_tools(AlwaysFailTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-soft-failure")

    wf.add_step("always_fail", continue_on_error=True)

    kernel.workflow.execute(wf)

    progress = collector.payloads("workflow.progress")
    assert progress[0]["status"] == "failed_ignored"
    assert collector.names()[-1] == "workflow.completed"
    assert "workflow.failed" not in collector.names()


def test_hard_failure_emits_failed_progress_status_then_workflow_failed():
    kernel = _kernel_with_tools(AlwaysFailTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-hard-failure")

    wf.add_step("always_fail")

    try:
        kernel.workflow.execute(wf)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected the step failure to propagate.")

    progress = collector.payloads("workflow.progress")
    assert progress[0]["status"] == "failed"

    assert collector.names() == [
        "workflow.started",
        "workflow.progress",
        "workflow.failed",
    ]

    failed = collector.payloads("workflow.failed")[0]
    assert "boom" in failed["error"]
    assert failed["duration"] >= 0


def test_parallel_group_progress_counts_every_branch_exactly_once():
    kernel = _kernel_with_tools(EchoTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-parallel-progress")

    with wf.parallel():
        wf.add_step("echo", value="a")
        wf.add_step("echo", value="b")
        wf.add_step("echo", value="c")

    kernel.workflow.execute(wf)

    started = collector.payloads("workflow.started")[0]
    assert started["total_steps"] == 3

    progress = collector.payloads("workflow.progress")
    assert len(progress) == 3
    # Branches run concurrently, so completion order isn't guaranteed, but
    # the shared counter must still hand out 1, 2, 3 with no duplicates
    # or gaps, and the final event must reach 100%.
    assert sorted(p["completed"] for p in progress) == [1, 2, 3]
    assert progress[-1]["percent"] == 100

    assert collector.names()[0] == "workflow.started"
    assert collector.names()[-1] == "workflow.completed"


def test_parallel_group_failure_still_emits_progress_for_every_branch():
    kernel = _kernel_with_tools(EchoTool(), AlwaysFailTool())
    collector = _EventCollector(kernel)
    wf = Workflow("events-parallel-failure")

    with wf.parallel():
        wf.add_step("echo", value="ok")
        wf.add_step("always_fail")

    try:
        kernel.workflow.execute(wf)
    except WorkflowGroupError:
        pass
    else:
        raise AssertionError("Expected WorkflowGroupError.")

    # Both branches ran to completion (per the group's run-to-completion
    # contract), so both should have reported progress before the group
    # error surfaced and workflow.failed fired.
    progress = collector.payloads("workflow.progress")
    assert sorted(p["status"] for p in progress) == ["failed", "succeeded"]
    assert collector.names()[-1] == "workflow.failed"
