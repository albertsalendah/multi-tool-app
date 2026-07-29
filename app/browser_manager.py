from __future__ import annotations

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Playwright


class BrowserManager:
    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def initialize(self, headless: bool = True):
        if self._browser is not None:
            return

        self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=headless
        )

    def shutdown(self):
        if self._browser:
            self._browser.close()
            self._browser = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def new_context(self, **kwargs) -> BrowserContext:
        if self._browser is None:
            raise RuntimeError("BrowserManager has not been initialized.")

        return self._browser.new_context(**kwargs)

    def new_page(self, **kwargs):
        context = self.new_context(**kwargs)
        return context.new_page()

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("BrowserManager has not been initialized.")

        return self._browser