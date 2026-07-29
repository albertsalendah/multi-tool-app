from __future__ import annotations

import re
from copy import deepcopy
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

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

    def _execute_step(
        self,
        step: WorkflowStep,
        workflow: Workflow,
        background: bool,
    ) -> list:
        """Run a single step with its condition/retry/continue_on_error rules.

        Returns a list containing the result (0 or 1 items) so callers can
        uniformly `.extend()` regardless of node type.
        """

        if not self._evaluate_condition(step.condition, workflow):
            return []

        attempt = 0

        while True:

            try:

                result = self._run_step(step, workflow, background)

                if step.result_as:
                    workflow.state.set(step.result_as, result)

                return [result]

            except Exception:
                # concurrent.futures.TimeoutError is an Exception subclass,
                # so it's already covered here.

                if attempt >= step.retry:

                    if step.continue_on_error:
                        return []

                    raise

            attempt += 1

    def _execute_group(
        self,
        group: ParallelGroup,
        workflow: Workflow,
        background: bool,
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
                result = self._execute_node(node, workflow, background)

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
    ) -> list:

        if isinstance(node, ParallelGroup):
            return self._execute_group(node, workflow, background)

        return self._execute_step(node, workflow, background)

    def execute(
        self,
        workflow: Workflow,
        background=False,
    ):

        results = []

        for node in workflow:
            results.extend(self._execute_node(node, workflow, background))

        return results
