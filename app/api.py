from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.kernel import ApplicationKernel

router = APIRouter(prefix="/api/v1", tags=["platform-api"])


# --------------------------------------------------------------------------
# Kernel access
# --------------------------------------------------------------------------
#
# The kernel is created once and stored on app.state by main.py's lifespan
# handler. Reading it via a dependency (rather than a module-level global)
# keeps this router import-safe and lets tests substitute a fake kernel
# with FastAPI's dependency_overrides instead of monkeypatching a global.


def get_kernel(request: Request) -> ApplicationKernel:
    return request.app.state.kernel


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ToolInfo(BaseModel):
    name: str
    version: str
    description: str


class HealthResponse(BaseModel):
    status: str
    initialized: bool


class CreateJobRequest(BaseModel):
    tool: str = Field(..., description="Registered tool name, see GET /tools.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed through to the tool's run().",
    )


class CreateJobResponse(BaseModel):
    job_id: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    result: Any = None
    error: str | None = None


class CancelJobResponse(BaseModel):
    job_id: str
    cancelled: bool


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health(kernel: ApplicationKernel = Depends(get_kernel)):
    return HealthResponse(status="ok", initialized=kernel.is_initialized)


@router.get("/tools", response_model=list[ToolInfo])
def list_tools(kernel: ApplicationKernel = Depends(get_kernel)):
    return kernel.registry.list_tool_info()


@router.post("/jobs", response_model=CreateJobResponse, status_code=202)
def create_job(
    body: CreateJobRequest,
    kernel: ApplicationKernel = Depends(get_kernel),
):
    try:
        job_id = kernel.run_tool(body.tool, background=True, **body.params)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown tool: '{body.tool}'"
        )
    except (RuntimeError, ValueError) as exc:
        # Permission/manifest problems (missing capability, bad params
        # binding, etc) are the caller's to fix, not a server error.
        raise HTTPException(status_code=400, detail=str(exc))

    return CreateJobResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, kernel: ApplicationKernel = Depends(get_kernel)):
    job = kernel.jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        job_id=job.id,
        status=job.status.value,
        progress=job.progress,
        result=job.result,
        error=job.error,
    )


@router.delete("/jobs/{job_id}", response_model=CancelJobResponse)
def cancel_job(job_id: str, kernel: ApplicationKernel = Depends(get_kernel)):
    job = kernel.jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    cancelled = kernel.jobs.cancel(job_id)

    return CancelJobResponse(job_id=job_id, cancelled=cancelled)
