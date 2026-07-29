from __future__ import annotations

from app.capabilities import Capability


class PermissionManager:
    def __init__(self):
        self._services = {
            Capability.BROWSER: "browser",
            Capability.NETWORK: None,
            Capability.FILESYSTEM: None,
            Capability.CAPTCHA: None,
            Capability.CLIPBOARD: None,
            Capability.DATABASE: None,
        }

    def validate(self, manifest, container):
        for capability in manifest.capabilities:
            capability = Capability(capability)

            service = self._services.get(capability)

            if service is None:
                continue

            if not container.has(service):
                raise RuntimeError(f"Missing required capability: {capability.value}")
