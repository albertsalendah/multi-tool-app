from __future__ import annotations

import re
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.workflow import Workflow

_VARIABLE_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


class WorkflowEngine:
    def __init__(self, kernel):
        self.kernel = kernel

    def _resolve_value(self, value, workflow):

        if isinstance(value, str):

            def replace(match):
                key = match.group(1).strip()
                value = workflow.context.get(key)

                return "" if value is None else str(value)

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
                workflow.context.data,
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

    def execute(
        self,
        workflow: Workflow,
        background=False,
    ):

        results = []

        for step in workflow:

            if not self._evaluate_condition(
                step.condition,
                workflow,
            ):
                continue

            attempt = 0

            while True:

                try:

                    result = self._run_step(
                        step,
                        workflow,
                        background,
                    )

                    results.append(result)

                    if step.result_as:
                        workflow.context.set(
                            step.result_as,
                            result,
                        )

                    break

                except TimeoutError:

                    if attempt >= step.retry:

                        if step.continue_on_error:
                            break

                        raise

                except Exception:

                    if attempt >= step.retry:

                        if step.continue_on_error:
                            break

                        raise

                attempt += 1

        return results
