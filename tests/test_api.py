import time

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


def _register(kernel: ApplicationKernel, tool: BaseTool):
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": []}
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
        {"name": "echo", "version": "1.0.0", "description": ""}
    ]


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
