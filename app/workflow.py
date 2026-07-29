from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

# ==========================================================
# Workflow State
# ==========================================================


class WorkflowState:
    """
    Shared data available to every step in a workflow.

    Access is lock-protected because ParallelGroup branches may read
    and write state concurrently from different threads.
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._lock = RLock()

    def set(self, key: str, value: Any):
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def has(self, key: str):
        with self._lock:
            return key in self._data

    def clear(self):
        with self._lock:
            self._data.clear()

    @property
    def data(self):
        # Snapshot rather than a live reference, since callers (e.g. the
        # condition evaluator) iterate this outside of the lock.
        with self._lock:
            return dict(self._data)


# ==========================================================
# Workflow Nodes
# ==========================================================


class WorkflowNode:
    """
    Base class for every workflow node.
    """

    pass


@dataclass(slots=True)
class WorkflowStep(WorkflowNode):

    tool: str

    params: dict[str, Any] = field(default_factory=dict)

    result_as: str | None = None

    condition: str | None = None

    retry: int = 0

    timeout: float | None = None

    continue_on_error: bool = False


@dataclass(slots=True)
class ParallelGroup(WorkflowNode):

    steps: list[WorkflowNode] = field(default_factory=list)

    def add(self, node: WorkflowNode):
        self.steps.append(node)

    def __iter__(self):
        return iter(self.steps)


# ==========================================================
# Workflow
# ==========================================================


class Workflow:

    def __init__(self, name: str):

        self.name = name

        self.state = WorkflowState()

        self.nodes: list[WorkflowNode] = []

        self._group_stack: list[ParallelGroup] = []

    # ------------------------------------------------------

    def add_step(
        self,
        tool: str,
        *,
        result_as: str | None = None,
        condition: str | None = None,
        retry: int = 0,
        timeout: float | None = None,
        continue_on_error: bool = False,
        **params,
    ):

        step = WorkflowStep(
            tool=tool,
            params=params,
            result_as=result_as,
            condition=condition,
            retry=retry,
            timeout=timeout,
            continue_on_error=continue_on_error,
        )

        if self._group_stack:
            self._group_stack[-1].add(step)
        else:
            self.nodes.append(step)

        return step

    # ------------------------------------------------------

    @contextmanager
    def parallel(self):

        group = ParallelGroup()

        if self._group_stack:
            raise RuntimeError("Nested parallel groups are not supported yet.")

        self._group_stack.append(group)

        try:
            yield group

        finally:

            self._group_stack.pop()

            self.nodes.append(group)

    # ------------------------------------------------------

    def clear(self):

        self.nodes.clear()

        self.state.clear()

    # ------------------------------------------------------

    def __iter__(self):

        return iter(self.nodes)

    # ------------------------------------------------------

    def __len__(self):

        return len(self.nodes)
