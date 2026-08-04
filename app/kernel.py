from __future__ import annotations
from app.events import EventBus
from app.tool_registry import ToolRegistry
from app.job_manager import JobManager
from app.browser_manager import BrowserManager
from app.config import Config
from app.logger import Logger
from app.container import ServiceContainer
from app.permission_manager import PermissionManager
from app.execution_context import ExecutionContext
from app.scheduler import Scheduler
from app.workflow_engine import WorkflowEngine
from tools.base_tool import ToolValidationError


class ApplicationKernel:
    def __init__(self):
        self.config = Config()
        self.logger = Logger(
            level=self.config.get("logging.level", "INFO"),
            log_file=self.config.get("logging.file", "logs/app.log"),
            console=self.config.get("logging.console", True),
            file_output=self.config.get("logging.file_output", True),
        )
        self.permissions = PermissionManager()
        self.container = ServiceContainer()
        self.registry = ToolRegistry()
        self.browser = BrowserManager(
            default_headless=self.config.get("browser.headless", True)
        )
        self._initialized = False
        self.events = EventBus()
        self.jobs = JobManager(
            event_bus=self.events,
            max_workers=self.config.get("jobs.max_workers", 4),
        )
        self.scheduler = Scheduler(self.jobs)
        self.workflow = WorkflowEngine(self)

    def initialize(self):
        if self._initialized:
            return
        log = self.logger.logger
        self.container.register("permissions", self.permissions)
        self.registry.discover_tools()

        self._initialized = True

        self.events.subscribe(
            "tool.started", lambda tool: log.info(f"Tool started: {tool}")
        )

        self.events.subscribe(
            "tool.finished", lambda tool, result: log.info(f"Tool finished: {tool}")
        )

        self.events.subscribe(
            "job.started", lambda job_id: log.info(f"Job started: {job_id}")
        )

        self.events.subscribe(
            "job.completed", lambda job_id, result: log.info(f"Job completed: {job_id}")
        )

        self.events.subscribe(
            "job.failed",
            lambda job_id, error: log.error(f"Job failed: {job_id} ({error})"),
        )

        self.events.subscribe(
            "job.cancelled", lambda job_id: log.warning(f"Job cancelled: {job_id}")
        )

        self.events.subscribe(
            "tool.progress",
            lambda tool, progress, message: log.info(
                f"[{tool}] {progress}% - {message}"
            ),
        )

        self.events.subscribe(
            "workflow.started",
            lambda workflow, execution_id, total_steps, background: log.info(
                f"Workflow started: {workflow} ({execution_id}) - {total_steps} step(s)"
            ),
        )

        self.events.subscribe(
            "workflow.progress",
            lambda workflow, execution_id, tool, status, completed, total, percent: log.info(
                f"[{workflow}] {percent}% ({completed}/{total}) - {tool}: {status}"
            ),
        )

        self.events.subscribe(
            "workflow.completed",
            lambda workflow, execution_id, duration, result_count: log.info(
                f"Workflow completed: {workflow} ({execution_id}) - "
                f"{result_count} result(s) in {duration:.2f}s"
            ),
        )

        self.events.subscribe(
            "workflow.failed",
            lambda workflow, execution_id, duration, error: log.error(
                f"Workflow failed: {workflow} ({execution_id}) - {error}"
            ),
        )

        self.container.register("config", self.config)
        self.container.register("logger", self.logger)
        self.container.register("events", self.events)
        self.container.register("jobs", self.jobs)
        self.container.register("scheduler", self.scheduler)
        self.container.register("browser", self.browser)
        self.container.register("registry", self.registry)
        self.container.register(
            "workflow",
            self.workflow,
        )

    def shutdown(self):
        if not self._initialized:
            return

        self.scheduler.shutdown()
        self.jobs.shutdown()
        self.browser.shutdown()

        self._initialized = False

    def list_tools(self):
        return self.registry.list_tools()

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def get_tool(self, name: str):
        return self.registry.get_tool(name)

    def _run_tool_lifecycle(self, tool, context, kwargs):
        """initialize() -> validate() -> run() -> cleanup(), for one
        execution. cleanup() always runs, even if validate() rejects the
        request or run() raises - mirrors ADR-0002's per-job resource
        lifecycle, not a one-time app-startup thing."""

        tool.initialize(context)

        try:
            if not tool.validate(context.request):
                raise ToolValidationError(
                    f"Validation failed for tool '{context.tool_name}'."
                )

            return tool.run(**kwargs)

        finally:
            tool.cleanup(context)

    def run_tool(self, name: str, background: bool = False, **kwargs):
        manifest = self.registry.get_manifest(name)

        self.permissions.validate(
            manifest,
            self.container,
        )
        tool = self.get_tool(name)

        context = (
            ExecutionContext(
                tool_name=name,
                services=self.container,
                request=kwargs,
            )
            if background
            else ExecutionContext.for_foreground(
                tool_name=name,
                services=self.container,
                request=kwargs,
            )
        )
        kwargs["context"] = context

        self.events.emit(
            "tool.started",
            tool=name,
        )

        def _run_and_announce():
            # Mirrors the old sync-only path: tool.finished fires once the
            # lifecycle succeeds, not on failure/cancellation (JobManager's
            # own job.completed/job.failed events already cover those).
            # Used for both foreground and background now, so this no
            # longer only fires for synchronous execution.
            result = self._run_tool_lifecycle(tool, context, kwargs)
            self.events.emit("tool.finished", tool=name, result=result)
            return result

        if background:
            return self.jobs.submit(_run_and_announce, context=context)

        return _run_and_announce()

    def run_workflow(
        self,
        workflow,
        background=False,
    ):
        return self.workflow.execute(
            workflow,
            background=background,
        )
