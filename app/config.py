from __future__ import annotations

import os
from pathlib import Path

import yaml


class Config:
    def __init__(self, config_file: str = "config/default.yaml"):
        self._data = {}

        path = Path(config_file)

        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}

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
