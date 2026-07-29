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
        self.browser = BrowserManager()
        self._initialized = False
        self.events = EventBus()
        self.jobs = JobManager(
            event_bus=self.events,
            max_workers=self.config.get("jobs.max_workers", 4),
        )
        self.scheduler = Scheduler(self.jobs)

    def initialize(self):
        if self._initialized:
            return
        log = self.logger.logger
        self.container.register("permissions", self.permissions)
        self.browser.initialize(headless=self.config.get("browser.headless", True))
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

        self.container.register("config", self.config)
        self.container.register("logger", self.logger)
        self.container.register("events", self.events)
        self.container.register("jobs", self.jobs)
        self.container.register("scheduler", self.scheduler)
        self.container.register("browser", self.browser)
        self.container.register("registry", self.registry)

    def shutdown(self):
        if not self._initialized:
            return

        self.scheduler.shutdown()
        self.jobs.shutdown()
        self.browser.shutdown()

        self._initialized = False

    def list_tools(self):
        return self.registry.list_tools()

    def get_tool(self, name: str):
        return self.registry.get_tool(name)

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
        kwargs.setdefault("services", self.container)
        kwargs.setdefault("context", context)

        self.events.emit(
            "tool.started",
            tool=name,
        )

        if background:
            return self.jobs.submit(lambda: tool.run(**kwargs), context=context)

        result = tool.run(**kwargs)

        self.events.emit(
            "tool.finished",
            tool=name,
            result=result,
        )

        return result
