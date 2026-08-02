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
            return os.environ[env_key]

        value = self._data

        for part in key.split("."):
            if not isinstance(value, dict):
                return default

            value = value.get(part)

            if value is None:
                return default

        return value
