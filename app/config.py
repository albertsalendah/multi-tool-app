from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

log = logging.getLogger("MultiToolApp")


class Config:
    def __init__(self, config_file: str = "config/default.yaml"):
        self._data = {}

        path = Path(config_file)

        if not path.exists():
            # Config() is constructed before Logger sets up this app's
            # own handlers (see ApplicationKernel.__init__), so this
            # goes to Python's logging "handler of last resort"
            # (stderr) rather than the configured log file/console
            # handlers - still visible, just not in the usual place.
            log.warning(
                f"Config file '{config_file}' not found - using defaults."
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            log.warning(
                f"Config file '{config_file}' is malformed ({exc}) - using defaults."
            )
            self._data = {}

    def get(self, key: str, default=None):
        env_key = key.upper().replace(".", "_")

        if env_key in os.environ:
            return self._coerce(os.environ[env_key], default, env_key)

        value = self._data

        for part in key.split("."):
            if not isinstance(value, dict):
                return default

            value = value.get(part)

            if value is None:
                return default

        return value

    @staticmethod
    def _coerce(raw: str, default, env_key: str):
        """Env vars are always strings; coerce to the type implied by the
        caller's default so `config.get("jobs.max_workers", 4)` returns an
        int (not "8"), and `config.get("browser.headless", True)` treats
        "false" as False instead of a truthy non-empty string.

        bool must be checked before int - isinstance(True, int) is True."""
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")

        if isinstance(default, int):
            try:
                return int(raw)
            except ValueError:
                log.warning(
                    f"Env var '{env_key}'={raw!r} is not a valid int - "
                    f"using default {default!r}."
                )
                return default

        if isinstance(default, float):
            try:
                return float(raw)
            except ValueError:
                log.warning(
                    f"Env var '{env_key}'={raw!r} is not a valid float - "
                    f"using default {default!r}."
                )
                return default

        return raw
