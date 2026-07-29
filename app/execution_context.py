from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from types import MappingProxyType
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from app.cancellation import CancellationToken

if TYPE_CHECKING:
    from app.container import ServiceContainer


class ExecutionContext:
    """Per-execution data shared by the platform and a running tool."""

    def __init__(
        self,
        *,
        tool_name: str,
        services: ServiceContainer,
        request: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        self.job_id = job_id
        self.tool_name = tool_name
        self.services = services
        self.request = MappingProxyType(dict(request or {}))
        self.cancellation_token = cancellation_token or CancellationToken()
        self._state: dict[str, Any] = {}
        self._lock = RLock()

    @classmethod
    def for_foreground(
        cls,
        *,
        tool_name: str,
        services: ServiceContainer,
        request: Mapping[str, Any] | None = None,
    ) -> ExecutionContext:
        return cls(
            job_id=str(uuid4()),
            tool_name=tool_name,
            services=services,
            request=request,
        )

    def bind_job(self, job_id: str) -> None:
        """Bind a queued execution to the Job Manager's canonical ID."""
        if self.job_id is not None and self.job_id != job_id:
            raise ValueError("Execution context is already bound to another job.")

        self.job_id = job_id

    def get_service(self, name: str) -> Any:
        return self.services.get(name)

    def is_cancelled(self) -> bool:
        return self.cancellation_token.is_cancelled()

    def raise_if_cancelled(self) -> None:
        self.cancellation_token.raise_if_cancelled()

    def set_state(self, key: str, value: Any) -> None:
        with self._lock:
            self._state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.get(key, default)

    def pop_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.pop(key, default)

    def state_snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return MappingProxyType(dict(self._state))
