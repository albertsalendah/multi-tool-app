from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.capabilities import Capability
from app.kernel import ApplicationKernel

router = APIRouter(prefix="/api/v1", tags=["platform-api"])

# kernel.run_tool(name, background=..., **params) binds these two
# positionally/by-keyword itself - if a client's params dict also
# contains either key, Python raises "got multiple values for
# argument" (a TypeError, uncaught anywhere else in this router),
# surfacing as an ugly unhandled 500 instead of a clear client error.
_RESERVED_PARAM_NAMES = {"name", "background"}


def _reject_reserved_params(params: dict) -> None:
    collisions = _RESERVED_PARAM_NAMES & params.keys()

    if collisions:
        raise HTTPException(
            status_code=400,
            detail=(
                "params cannot use reserved name(s): "
                f"{', '.join(sorted(collisions))}"
            ),
        )


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
    capabilities: list[str] = []


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


class RunToolRequest(BaseModel):
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed through to the tool's run().",
    )


class RunToolResponse(BaseModel):
    result: Any = None


class CreateScheduleRequest(BaseModel):
    delay_seconds: float = Field(
        ..., ge=0, description="Seconds from now to run the tool."
    )
    tool: str = Field(..., description="Registered tool name, see GET /tools.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed through to the tool's run().",
    )


class CreateScheduleResponse(BaseModel):
    schedule_id: str


class ScheduleResponse(BaseModel):
    schedule_id: str
    status: str
    run_at: str
    job_id: str | None = None


class CancelScheduleResponse(BaseModel):
    schedule_id: str
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
    _reject_reserved_params(body.params)

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

    snapshot = job.snapshot()

    return JobResponse(
        job_id=snapshot.id,
        status=snapshot.status.value,
        progress=snapshot.progress,
        result=snapshot.result,
        error=snapshot.error,
    )


@router.delete("/jobs/{job_id}", response_model=CancelJobResponse)
def cancel_job(job_id: str, kernel: ApplicationKernel = Depends(get_kernel)):
    job = kernel.jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    cancelled = kernel.jobs.cancel(job_id)

    return CancelJobResponse(job_id=job_id, cancelled=cancelled)


@router.post("/tools/{name}/run", response_model=RunToolResponse)
def run_tool_sync(
    name: str,
    body: RunToolRequest,
    kernel: ApplicationKernel = Depends(get_kernel),
):
    """Run a tool synchronously and return its result directly - for
    fast, non-browser tools where job creation + polling would be pure
    overhead. Long-running/interactive tools (declared 'browser'
    capability) are refused here; use POST /jobs for those instead."""

    try:
        manifest = kernel.registry.get_manifest(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown tool: '{name}'")

    if Capability.BROWSER in manifest.capabilities:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tool '{name}' requires the 'browser' capability and may "
                "run for a long time (e.g. manual CAPTCHA solving) - use "
                "POST /jobs instead of this synchronous endpoint."
            ),
        )

    _reject_reserved_params(body.params)

    # Tool existence was already confirmed via get_manifest() above, so a
    # KeyError from here on is the tool's own bug, not "unknown tool" -
    # let it surface as an uncaught 500 instead of a misleading 404.
    try:
        result = kernel.run_tool(name, background=False, **body.params)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RunToolResponse(result=result)


@router.post("/schedules", response_model=CreateScheduleResponse, status_code=202)
def create_schedule(
    body: CreateScheduleRequest,
    kernel: ApplicationKernel = Depends(get_kernel),
):
    _reject_reserved_params(body.params)

    try:
        schedule_id = kernel.schedule_tool(
            body.delay_seconds, body.tool, **body.params
        )
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown tool: '{body.tool}'"
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CreateScheduleResponse(schedule_id=schedule_id)


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(schedule_id: str, kernel: ApplicationKernel = Depends(get_kernel)):
    scheduled = kernel.scheduler.get(schedule_id)

    if scheduled is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return ScheduleResponse(
        schedule_id=scheduled.id,
        status=str(kernel.scheduler.status(schedule_id)),
        run_at=scheduled.run_at.isoformat(),
        job_id=scheduled.job_id,
    )


@router.delete("/schedules/{schedule_id}", response_model=CancelScheduleResponse)
def cancel_schedule(schedule_id: str, kernel: ApplicationKernel = Depends(get_kernel)):
    scheduled = kernel.scheduler.get(schedule_id)

    if scheduled is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    cancelled = kernel.scheduler.cancel(schedule_id)

    return CancelScheduleResponse(schedule_id=schedule_id, cancelled=cancelled)
