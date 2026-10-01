"""Tariff helpers, also exposed to templates as ``macros.meter.*``."""

from __future__ import annotations

PEAK_HOURS = range(16, 21)  # 16:00-20:59 UTC


def tariff_band(hour: int) -> str:
    """Tariff band of a UTC hour of day."""
    return "peak" if int(hour) in PEAK_HOURS else "offpeak"


def invoice_batch(day: str) -> str:
    """Invoice batch id finance expects for a billing day (YYYY-MM-DD)."""
    return "INV-" + str(day).replace("-", "")
