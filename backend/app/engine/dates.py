"""Calendar rules for due dates (all dates are plain IST calendar days)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.engine.types import Frequency


def add_months(start: date, months: int, anchor_day: int | None = None) -> date:
    """Add months keeping the anchor day; short months use their last day (PRD section 4).

    A loan due on the 31st is due on 28/29 Feb and back on 31 Mar, because the anchor is the
    first due day, not the previous (clamped) date.
    """
    day = anchor_day if anchor_day is not None else start.day
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def one_period_after(start: date, frequency: Frequency) -> date:
    if frequency is Frequency.MONTHLY or frequency is Frequency.SINGLE:
        return add_months(start, 1)
    if frequency is Frequency.WEEKLY:
        return start + timedelta(days=7)
    return start + timedelta(days=1)


def due_dates(first_due: date, count: int, frequency: Frequency) -> list[date]:
    if frequency is Frequency.MONTHLY:
        return [add_months(first_due, k, anchor_day=first_due.day) for k in range(count)]
    step = 7 if frequency is Frequency.WEEKLY else 1
    return [first_due + timedelta(days=step * k) for k in range(count)]


def days_between(start: date, end: date) -> int:
    return (end - start).days
