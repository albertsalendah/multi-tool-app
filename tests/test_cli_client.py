from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router as platform_api_router
from app.kernel import ApplicationKernel
from cli.client import ApiClient, ApiError
from tools.base_tool import BaseTool


class EchoTool(BaseTool):
    name = "echo"

    def run(self, *, context=None, **kwargs):
        return kwargs.get("value")


def _register(kernel: ApplicationKernel, tool: BaseTool):
    kernel.registry.register(tool)
    kernel.registry._manifests[tool.name] = type(
        "Manifest", (), {"capabilities": []}
    )()


def _client_for(kernel: ApplicationKernel) -> ApiClient:
    app = FastAPI()
    app.include_router(platform_api_router)
    app.state.kernel = kernel

    # TestClient is a sync-compatible httpx.Client subclass bridged to the
    # ASGI app - unlike httpx.ASGITransport (async-only), it works with
    # ApiClient's sync requests, which is what the real CLI uses too.
    return ApiClient(base_url="http://testserver", http_client=TestClient(app))


def test_health_reflects_kernel_state():
    kernel = ApplicationKernel()
    client = _client_for(kernel)

    assert client.health() == {"status": "ok", "initialized": False}


def test_list_tools_returns_registered_tools():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_for(kernel)

    assert client.list_tools() == [
        {"name": "echo", "version": "1.0.0", "description": "", "capabilities": []}
    ]


def test_create_and_get_job_round_trip():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_for(kernel)

    try:
        created = client.create_job("echo", {"value": 7})
        job_id = created["job_id"]

        kernel.jobs.wait(job_id, timeout=1)

        job = client.get_job(job_id)
        assert job["status"] == "completed"
        assert job["result"] == 7
    finally:
        kernel.jobs.shutdown()


def test_wait_for_job_polls_until_terminal():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_for(kernel)

    try:
        created = client.create_job("echo", {"value": "done"})
        job = client.wait_for_job(created["job_id"], poll_interval=0.01, timeout=2)

        assert job["status"] == "completed"
        assert job["result"] == "done"
    finally:
        kernel.jobs.shutdown()


def test_cancel_job():
    kernel = ApplicationKernel()
    _register(kernel, EchoTool())
    client = _client_for(kernel)

    try:
        created = client.create_job("echo", {"value": 1})
        kernel.jobs.wait(created["job_id"], timeout=1)

        # Already completed by the time we cancel - cancel() itself is
        # still a well-formed call, just a no-op cancellation.
        result = client.cancel_job(created["job_id"])
        assert result["job_id"] == created["job_id"]
    finally:
        kernel.jobs.shutdown()


def test_create_job_for_unknown_tool_raises_api_error_with_404():
    kernel = ApplicationKernel()
    client = _client_for(kernel)

    try:
        client.create_job("does_not_exist")
    except ApiError as exc:
        assert exc.status_code == 404
        assert "does_not_exist" in str(exc)
    else:
        raise AssertionError("Expected ApiError.")


def test_get_unknown_job_raises_api_error_with_404():
    kernel = ApplicationKernel()
    client = _client_for(kernel)

    try:
        client.get_job("does-not-exist")
    except ApiError as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected ApiError.")


def test_connection_failure_raises_api_error_without_status_code():
    # No transport override - real network, guaranteed-unreachable port.
    client = ApiClient(base_url="http://127.0.0.1:1", timeout=2)

    try:
        client.health()
    except ApiError as exc:
        assert exc.status_code is None
        assert "127.0.0.1:1" in str(exc)
    else:
        raise AssertionError("Expected ApiError.")
