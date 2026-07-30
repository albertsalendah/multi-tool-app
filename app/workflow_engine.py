from __future__ import annotations

import re
import time
from copy import deepcopy
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.workflow import ParallelGroup, Workflow, WorkflowStep

_VARIABLE_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


class WorkflowGroupError(RuntimeError):
    """
    Raised when one or more branches of a ParallelGroup fail.

    All branches are allowed to run to completion (successful branches
    still write their results into WorkflowState) before this is raised,
    so a group failure never leaves other branches half-cancelled.
    """

    def __init__(self, failures: list[tuple[object, BaseException]]):
        self.failures = failures

        summary = "; ".join(
            f"{_node_label(node)}: {error}" for node, error in failures
        )

        super().__init__(f"{len(failures)} branch(es) failed: {summary}")


def _node_label(node) -> str:
    if isinstance(node, WorkflowStep):
        return node.tool
    return "parallel_group"


class _ProgressTracker:
    """
    Per-execution, thread-safe counter of completed leaf steps.

    A single tracker is shared across an entire execute() call, including
    every branch of every ParallelGroup, so `workflow.progress` events
    reflect progress across the whole workflow rather than one branch.
    """

    __slots__ = ("total", "completed", "workflow_name", "execution_id", "_lock")

    def __init__(self, total: int, workflow_name: str, execution_id: str):
        self.total = total
        self.completed = 0
        self.workflow_name = workflow_name
        self.execution_id = execution_id
        self._lock = Lock()

    def increment(self) -> int:
        with self._lock:
            self.completed += 1
            return self.completed


class WorkflowEngine:
    def __init__(self, kernel):
        self.kernel = kernel

    def _resolve_value(self, value, workflow):

        if isinstance(value, str):

            def replace(match):
                key = match.group(1).strip()
                resolved = workflow.state.get(key)

                return "" if resolved is None else str(resolved)

            return _VARIABLE_PATTERN.sub(replace, value)

        if isinstance(value, list):
            return [self._resolve_value(v, workflow) for v in value]

        if isinstance(value, dict):
            return {k: self._resolve_value(v, workflow) for k, v in value.items()}

        return value

    def _resolve_params(self, params, workflow):
        return self._resolve_value(
            deepcopy(params),
            workflow,
        )

    def _evaluate_condition(
        self,
        condition,
        workflow,
    ):
        if not condition:
            return True

        return bool(
            eval(
                condition,
                {},
                workflow.state.data,
            )
        )

    def _run_step(
        self,
        step,
        workflow,
        background,
    ):
        params = self._resolve_params(
            step.params,
            workflow,
        )

        if step.timeout is None:
            return self.kernel.run_tool(
                step.tool,
                background=background,
                **params,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:

            future = executor.submit(
                self.kernel.run_tool,
                step.tool,
                background,
                **params,
            )

            return future.result(
                timeout=step.timeout,
            )

    def _report_step_progress(self, tracker: _ProgressTracker, step: WorkflowStep, outcome: str):
        completed = tracker.increment()
        percent = int((completed / tracker.total) * 100) if tracker.total else 100

        self.kernel.events.emit(
            "workflow.progress",
            workflow=tracker.workflow_name,
            execution_id=tracker.execution_id,
            tool=step.tool,
            status=outcome,
            completed=completed,
            total=tracker.total,
            percent=percent,
        )

    def _execute_step(
        self,
        step: WorkflowStep,
        workflow: Workflow,
        background: bool,
        tracker: _ProgressTracker,
    ) -> list:
        """Run a single step with its condition/retry/continue_on_error rules.

        Returns a list containing the result (0 or 1 items) so callers can
        uniformly `.extend()` regardless of node type.
        """

        outcome = "skipped"

        try:

            if not self._evaluate_condition(step.condition, workflow):
                return []

            attempt = 0

            while True:

                try:

                    result = self._run_step(step, workflow, background)

                    if step.result_as:
                        workflow.state.set(step.result_as, result)

                    outcome = "succeeded"
                    return [result]

                except Exception:
                    # concurrent.futures.TimeoutError is an Exception subclass,
                    # so it's already covered here.

                    if attempt >= step.retry:

                        if step.continue_on_error:
                            outcome = "failed_ignored"
                            return []

                        outcome = "failed"
                        raise

                attempt += 1

        finally:
            self._report_step_progress(tracker, step, outcome)

    def _execute_group(
        self,
        group: ParallelGroup,
        workflow: Workflow,
        background: bool,
        tracker: _ProgressTracker,
    ) -> list:
        """Run every branch of a ParallelGroup concurrently.

        Every branch runs to completion regardless of sibling failures.
        Failures are collected and raised together as a single
        WorkflowGroupError once all branches finish (option a: run to
        completion, then aggregate).
        """

        branch_results: list[list] = [[] for _ in group.steps]
        failures: list[tuple[object, BaseException]] = []
        lock = Lock()

        def run_branch(index: int, node) -> None:
            try:
                result = self._execute_node(node, workflow, background, tracker)

                with lock:
                    branch_results[index] = result

            except BaseException as exc:  # noqa: BLE001 - collected, not swallowed
                with lock:
                    failures.append((node, exc))

        with ThreadPoolExecutor(max_workers=max(len(group.steps), 1)) as executor:

            futures = [
                executor.submit(run_branch, index, node)
                for index, node in enumerate(group.steps)
            ]

            for future in futures:
                # run_branch never re-raises; this just waits for completion.
                future.result()

        if failures:
            raise WorkflowGroupError(failures)

        flattened: list = []

        for result in branch_results:
            flattened.extend(result)

        return flattened

    def _execute_node(
        self,
        node,
        workflow: Workflow,
        background: bool,
        tracker: _ProgressTracker,
    ) -> list:

        if isinstance(node, ParallelGroup):
            return self._execute_group(node, workflow, background, tracker)

        return self._execute_step(node, workflow, background, tracker)

    def _count_steps(self, nodes) -> int:
        """Recursively count leaf WorkflowSteps, including inside nested
        ParallelGroups, so progress percentages are accurate up front."""

        total = 0

        for node in nodes:
            if isinstance(node, ParallelGroup):
                total += self._count_steps(node.steps)
            else:
                total += 1

        return total

    def execute(
        self,
        workflow: Workflow,
        background=False,
    ):

        execution_id = str(uuid4())
        total = self._count_steps(workflow.nodes)
        tracker = _ProgressTracker(total, workflow.name, execution_id)

        self.kernel.events.emit(
            "workflow.started",
            workflow=workflow.name,
            execution_id=execution_id,
            total_steps=total,
            background=background,
        )

        start = time.perf_counter()

        try:
            results = []

            for node in workflow:
                results.extend(
                    self._execute_node(node, workflow, background, tracker)
                )

        except Exception as exc:
            self.kernel.events.emit(
                "workflow.failed",
                workflow=workflow.name,
                execution_id=execution_id,
                duration=time.perf_counter() - start,
                error=str(exc),
            )
            raise

        self.kernel.events.emit(
            "workflow.completed",
            workflow=workflow.name,
            execution_id=execution_id,
            duration=time.perf_counter() - start,
            result_count=len(results),
        )

        return results
