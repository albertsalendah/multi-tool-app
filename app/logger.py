from __future__ import annotations

import logging
from pathlib import Path


class Logger:
    def __init__(
        self,
        level: str = "INFO",
        log_file: str = "logs/app.log",
        console: bool = True,
        file_output: bool = True,
    ):
        self._logger = logging.getLogger("MultiToolApp")
        self._logger.setLevel(getattr(logging, level.upper()))

        self._logger.handlers.clear()

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        if file_output:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(
                log_file,
                encoding="utf-8",
            )

            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

    @property
    def logger(self):
        return self._logger
