import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import get_kernel
from app.api import router as platform_api_router
from app.kernel import ApplicationKernel
from tools.base_tool import BaseTool


class EchoTool(BaseTool):
    name = "echo"

    def run(self, *, context=None, **kwargs):
        return kwargs.get("value")


class CooperativeTool(BaseTool):
    """Loops checking the cancellation token, same pattern used in
    tests/test_execution_context.py - lets us test a real running job
    actually stopping when cancelled through the API."""

    name = "cooperative"

    def run(self, *, context=None, **kwargs):
        while True:
            context.raise_if_cancelled()
            time.sleep(0.005)


def _register(kernel: ApplicationKernel, tool: BaseTool, capabilities: list[str] = None):
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": capabilities or []}
    )()


def _client_with_kernel(kernel: ApplicationKernel) -> TestClient:
    """A bare FastAPI app carrying only the platform API router, with the
    kernel swapped in via dependency_overrides - deliberately not main.py's
    real app, so these tests don't need seleniumbase/yt-dlp/a real browser
    just to exercise the platform-level endpoints."""

    app = FastAPI()
    app.include_router(platform_api_router)
    app.dependency_overrides[get_kernel] = lambda: kernel
    return TestClient(app)


# --------------------------------------------------------------------------
# GET /api/v1/health
# --------------------------------------------------------------------------


def test_health_reports_initialization_status():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "initialized": False}


# --------------------------------------------------------------------------
# GET /api/v1/tools
# --------------------------------------------------------------------------


def test_list_tools_returns_registered_tool_info():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "echo", "version": "1.0.0", "description": "", "capabilities": []}
    ]


def test_list_tools_exposes_a_tools_declared_capabilities():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool(), capabilities=["network", "filesystem"])
    client = _client_with_kernel(kernel)

    response = client.get("/api/v1/tools")

    assert response.json()[0]["capabilities"] == ["network", "filesystem"]


# --------------------------------------------------------------------------
# POST /api/v1/jobs, GET /api/v1/jobs/{id}
# --------------------------------------------------------------------------


def test_create_job_runs_the_tool_and_can_be_polled_to_completion():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    try:
        response = client.post(
            "/api/v1/jobs", json={"tool": "echo", "params": {"value": 42}}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        kernel.jobs.wait(job_id, timeout=1)

        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200

        body = response.json()
        assert body["job_id"] == job_id
        assert body["status"] == "completed"
        assert body["result"] == 42
        assert body["error"] is None
    finally:
        kernel.jobs.shutdown()


def test_create_job_for_unknown_tool_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/jobs", json={"tool": "nope", "params": {}})

    assert response.status_code == 404


def test_get_unknown_job_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.get("/api/v1/jobs/does-not-exist")

    assert response.status_code == 404


# --------------------------------------------------------------------------
# DELETE /api/v1/jobs/{id}
# --------------------------------------------------------------------------


def test_cancel_unknown_job_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.delete("/api/v1/jobs/does-not-exist")

    assert response.status_code == 404


# --------------------------------------------------------------------------
# POST/GET/DELETE /api/v1/schedules
# --------------------------------------------------------------------------


def test_create_schedule_runs_the_tool_after_the_delay_and_can_be_polled():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    try:
        response = client.post(
            "/api/v1/schedules",
            json={"delay_seconds": 0.01, "tool": "echo", "params": {"value": 42}},
        )
        assert response.status_code == 202
        schedule_id = response.json()["schedule_id"]

        response = client.get(f"/api/v1/schedules/{schedule_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "scheduled"
        assert response.json()["job_id"] is None

        deadline = time.time() + 1
        job_id = None
        while job_id is None and time.time() < deadline:
            job_id = client.get(f"/api/v1/schedules/{schedule_id}").json()["job_id"]
            if job_id is None:
                time.sleep(0.01)

        assert job_id is not None
        kernel.jobs.wait(job_id, timeout=1)

        response = client.get(f"/api/v1/schedules/{schedule_id}")
        assert response.status_code == 200

        body = response.json()
        assert body["schedule_id"] == schedule_id
        assert body["status"] == "completed"
        assert body["job_id"] == job_id

        job_response = client.get(f"/api/v1/jobs/{job_id}")
        assert job_response.json()["result"] == 42
    finally:
        kernel.jobs.shutdown()


def test_create_schedule_for_unknown_tool_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.post(
        "/api/v1/schedules",
        json={"delay_seconds": 10, "tool": "nope", "params": {}},
    )

    assert response.status_code == 404


def test_create_schedule_rejects_reserved_param_name_background():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post(
        "/api/v1/schedules",
        json={"delay_seconds": 10, "tool": "echo", "params": {"background": "x"}},
    )

    assert response.status_code == 400
    assert "background" in response.json()["detail"]


def test_get_unknown_schedule_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.get("/api/v1/schedules/does-not-exist")

    assert response.status_code == 404


def test_cancel_unknown_schedule_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.delete("/api/v1/schedules/does-not-exist")

    assert response.status_code == 404


def test_cancel_schedule_before_it_fires():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    try:
        response = client.post(
            "/api/v1/schedules",
            json={"delay_seconds": 10, "tool": "echo", "params": {}},
        )
        schedule_id = response.json()["schedule_id"]

        response = client.delete(f"/api/v1/schedules/{schedule_id}")
        assert response.status_code == 200
        assert response.json() == {"schedule_id": schedule_id, "cancelled": True}

        response = client.get(f"/api/v1/schedules/{schedule_id}")
        assert response.json()["status"] == "cancelled"
    finally:
        kernel.jobs.shutdown()


def test_cancel_stops_a_running_cooperative_job():
    kernel = ApplicationKernel()
    _register(kernel, CooperativeTool())
    client = _client_with_kernel(kernel)

    try:
        response = client.post("/api/v1/jobs", json={"tool": "cooperative", "params": {}})
        job_id = response.json()["job_id"]

        # Let it actually start running before cancelling.
        time.sleep(0.05)

        response = client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id

        kernel.jobs.wait(job_id, timeout=1)

        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.json()["status"] == "cancelled"
    finally:
        kernel.jobs.shutdown()


# --------------------------------------------------------------------------
# POST /api/v1/tools/{name}/run
# --------------------------------------------------------------------------


class BrowserTool(BaseTool):
    """Declares the 'browser' capability - used to test that the sync
    endpoint refuses to run it (see app/api.py's run_tool_sync guard)."""

    name = "browser_tool"

    def run(self, *, context=None, **kwargs):
        return "should never get here"


class RaisingRuntimeTool(BaseTool):
    name = "raising_runtime"

    def run(self, *, context=None, **kwargs):
        raise RuntimeError("bad input")


class RaisingKeyErrorTool(BaseTool):
    """Simulates a tool with its own internal bug (not 'unknown tool') -
    confirms run_tool_sync doesn't misreport it as a 404. Manifest
    existence is already confirmed via get_manifest() before the tool
    ever runs, so a KeyError from here on is the tool's own bug."""

    name = "raising_keyerror"

    def run(self, *, context=None, **kwargs):
        raise KeyError("some_internal_key")


def test_run_sync_returns_the_tool_result_directly():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/tools/echo/run", json={"params": {"value": 99}})

    assert response.status_code == 200
    assert response.json() == {"result": 99}


def test_run_sync_unknown_tool_returns_404():
    kernel = ApplicationKernel()
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/tools/nope/run", json={"params": {}})

    assert response.status_code == 404


def test_run_sync_refuses_a_tool_that_declares_browser_capability():
    kernel = ApplicationKernel()
    _register(kernel, BrowserTool(), capabilities=["browser"])
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/tools/browser_tool/run", json={"params": {}})

    assert response.status_code == 400
    assert "browser" in response.json()["detail"]
    assert "/jobs" in response.json()["detail"]


def test_run_sync_maps_tool_runtime_error_to_400():
    kernel = ApplicationKernel()
    _register(kernel, RaisingRuntimeTool())
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/tools/raising_runtime/run", json={"params": {}})

    assert response.status_code == 400
    assert "bad input" in response.json()["detail"]


def test_run_sync_tool_internal_keyerror_is_not_misreported_as_unknown_tool():
    """Regression test: a tool's own KeyError bug used to be caught by
    the same 'except KeyError' guarding the unknown-tool case above and
    misreported as 404 'Unknown tool'. It should now surface uncaught
    (a real 500 outside of tests, where exceptions aren't re-raised)."""
    kernel = ApplicationKernel()
    _register(kernel, RaisingKeyErrorTool())
    client = _client_with_kernel(kernel)

    with pytest.raises(KeyError):
        client.post("/api/v1/tools/raising_keyerror/run", json={"params": {}})


def test_run_sync_defaults_params_to_empty_dict():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post("/api/v1/tools/echo/run", json={})

    assert response.status_code == 200
    assert response.json() == {"result": None}


# --------------------------------------------------------------------------
# Reserved param names (name/background collide with run_tool()'s own args)
# --------------------------------------------------------------------------


def test_create_job_rejects_reserved_param_name_background():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post(
        "/api/v1/jobs",
        json={"tool": "echo", "params": {"background": "x"}},
    )

    assert response.status_code == 400
    assert "background" in response.json()["detail"]


def test_create_job_rejects_reserved_param_name_name():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post(
        "/api/v1/jobs",
        json={"tool": "echo", "params": {"name": "x"}},
    )

    assert response.status_code == 400
    assert "name" in response.json()["detail"]


def test_run_sync_rejects_reserved_param_names():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    response = client.post(
        "/api/v1/tools/echo/run",
        json={"params": {"name": "x", "background": "y"}},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "name" in detail
    assert "background" in detail


def test_non_reserved_param_names_are_unaffected():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_with_kernel(kernel)

    try:
        response = client.post(
            "/api/v1/jobs", json={"tool": "echo", "params": {"value": 5}}
        )
        assert response.status_code == 202
    finally:
        kernel.jobs.shutdown()
