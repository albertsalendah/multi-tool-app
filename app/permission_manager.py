from __future__ import annotations

from app.capabilities import Capability


class PermissionManager:
    """Validates that a tool's declared capabilities can actually be
    satisfied before it runs.

    Only `browser` maps to a real, checkable container service today.
    The rest are declared-but-unenforced, deliberately, not by
    oversight:

    - `network` / `filesystem`: every tool already has unrestricted
      stdlib access to both - there's no sandboxing in this
      architecture that could gate them. Registering a trivial
      always-true marker service to "enforce" them wouldn't protect
      against anything, just add ceremony around a check that could
      never fail.
    - `clipboard` / `database`: no backing service exists in the
      platform yet. Nothing to check against.
    - `captcha`: a real library exists (libraries/captcha_manager), but
      it's instantiated directly per-browser-session by tools today,
      not exposed as a container service - wiring it up as one is a
      real architecture change, and part of the CAPTCHA-specific
      refinement work that's intentionally deferred, not this class's
      job to decide unilaterally.

    If a future platform service genuinely needs enforcing, add it to
    _services below with its container key, the same way `browser` is.
    """

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
