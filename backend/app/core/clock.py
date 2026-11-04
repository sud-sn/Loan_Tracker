"""The business day is the IST calendar day (PRD section 6)."""

from __future__ import annotations

from datetime import date, datetime

from app.config import IST

_override: date | None = None


def today() -> date:
    return _override or datetime.now(IST).date()


def set_today(value: date | None) -> None:
    """Tests only: pin the business day."""
    global _override
    _override = value
