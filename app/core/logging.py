from __future__ import annotations

import logging

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | " "%(filename)s:%(lineno)d | %(message)s"
)


def setup_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(level=level, format=LOG_FORMAT)
