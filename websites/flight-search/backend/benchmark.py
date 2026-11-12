"""Benchmark mode: freeze 'now' to a fixed date for deterministic behavior.

Activated by setting the BENCHMARK_PASSCODE environment variable to any
non-empty value.  When active, every backend call to ``today()`` or
``utcnow()`` returns a fixed point in time (2025-04-01 12:00 UTC) so that
prices, search windows, and booking timestamps are fully reproducible.
"""

import os
from datetime import date, datetime

BENCHMARK_DATE = date(2026, 4, 1)
BENCHMARK_DATETIME = datetime(2026, 4, 1, 12, 0, 0)

BENCHMARK_MODE: bool = bool(os.environ.get("BENCHMARK_PASSCODE", ""))


def today() -> date:
    """Return the current date, or the fixed benchmark date."""
    return BENCHMARK_DATE if BENCHMARK_MODE else date.today()


def utcnow() -> datetime:
    """Return the current UTC datetime, or the fixed benchmark datetime."""
    return BENCHMARK_DATETIME if BENCHMARK_MODE else datetime.utcnow()
