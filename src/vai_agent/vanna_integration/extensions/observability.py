"""Lightweight observability helpers for Vanna runtime events."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def observe_runtime_step(step: str, **fields: object) -> Iterator[None]:
    """Log duration and outcome for a runtime step without external deps."""

    started = time.perf_counter()
    try:
        yield
    except Exception:
        logger.exception(
            "runtime_step_failed",
            extra={"step": step, **fields},
        )
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "runtime_step_finished",
            extra={"step": step, "elapsed_ms": elapsed_ms, **fields},
        )
