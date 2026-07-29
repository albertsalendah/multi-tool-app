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

    def report_progress(
        self,
        progress: int,
        message: str = "",
    ):
        self.events.emit(
            "tool.progress",
            tool=self.tool_name,
            progress=progress,
            message=message,
            job_id=self.job_id,
        )

        self.set_state("progress", progress)

    def log_debug(self, message: str):
        self.logger.debug(message)

    def log_info(self, message: str):
        self.logger.info(message)

    def log_warning(self, message: str):
        self.logger.warning(message)

    def log_error(self, message: str):
        self.logger.error(message)

    @property
    def browser(self):
        return self.get_service("browser")

    @property
    def logger(self):
        return self.get_service("logger").logger

    @property
    def events(self):
        return self.get_service("events")

    @property
    def config(self):
        return self.get_service("config")

    @property
    def jobs(self):
        return self.get_service("jobs")

    @property
    def scheduler(self):
        return self.get_service("scheduler")

    @property
    def registry(self):
        return self.get_service("registry")
