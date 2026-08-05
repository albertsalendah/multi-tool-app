from __future__ import annotations

import os
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
ENV_BASE_URL = "MULTITOOL_API_URL"

TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


class ApiError(RuntimeError):
    """Raised for any non-2xx response or connection failure. Carries the
    server's error detail (or the connection failure message) as the
    exception text, and the HTTP status code when there is one."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class ApiClient:
    """Client for the platform REST API - see app/api.py and
    docs/implementation/API_REFERENCE.md for the endpoints this wraps."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url or os.environ.get(ENV_BASE_URL, DEFAULT_BASE_URL)
        self._http = http_client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ApiError(
                f"Could not reach the API at {self.base_url} - is the server running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiError(f"Request to {self.base_url}{path} timed out") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise ApiError(detail, status_code=response.status_code)

        return response.json()

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")

    def list_tools(self) -> list[dict]:
        return self._request("GET", "/api/v1/tools")

    def create_job(self, tool: str, params: dict | None = None) -> dict:
        return self._request(
            "POST", "/api/v1/jobs", json={"tool": tool, "params": params or {}}
        )

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def cancel_job(self, job_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/jobs/{job_id}")

    def create_schedule(
        self, delay_seconds: float, tool: str, params: dict | None = None
    ) -> dict:
        return self._request(
            "POST",
            "/api/v1/schedules",
            json={
                "delay_seconds": delay_seconds,
                "tool": tool,
                "params": params or {},
            },
        )

    def get_schedule(self, schedule_id: str) -> dict:
        return self._request("GET", f"/api/v1/schedules/{schedule_id}")

    def cancel_schedule(self, schedule_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/schedules/{schedule_id}")

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 0.5,
        timeout: float | None = None,
    ) -> dict:
        """Poll GET /jobs/{id} until it reaches a terminal status.

        There's no streaming/SSE endpoint yet (see EVENT_REFERENCE.md /
        ARCHITECTURE_CHANGELOG.md's Current Focus note), so this is the
        only way to wait for a job today.
        """
        start = time.monotonic()

        while True:
            job = self.get_job(job_id)

            if job["status"] in TERMINAL_JOB_STATUSES:
                return job

            if timeout is not None and (time.monotonic() - start) > timeout:
                raise ApiError(f"Timed out waiting for job '{job_id}' to finish")

            time.sleep(poll_interval)
