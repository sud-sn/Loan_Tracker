"""Late-penalty accrual, computed from the schedule and ledger at read time (PRD section 6).

Penalty accrues for each day ``d`` after an installment's due date on which the installment
was still unpaid at the start of the day (payments dated before ``d``). It never compounds:
it is charged on unpaid principal + interest only, and kept as its own line.

* ``PER_DAY``: a fixed amount per day while the loan has any overdue installment, booked
  against the oldest overdue installment that day.
* ``PCT_MONTH``: a percentage per month of each overdue installment's unpaid amount; one
  day is a thirtieth of a month.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext
from enum import StrEnum

from app.engine.money import ZERO, q2


class PenaltyMode(StrEnum):
    OFF = "off"
    PER_DAY = "per_day"
    PCT_MONTH = "pct_month"


@dataclass(frozen=True)
class PenaltyRule:
    mode: PenaltyMode
    value: Decimal  # rupees per day, or % per month
    grace_days: int = 0


@dataclass(frozen=True)
class PenaltyItem:
    item_id: str
    due_date: date
    amount_due: Decimal  # principal + interest of the installment, after waivers


@dataclass(frozen=True)
class PaidEvent:
    item_id: str
    on: date
    amount: Decimal  # principal + interest paid (negative for a reversal)


def accrued_penalty(
    items: list[PenaltyItem], events: list[PaidEvent], rule: PenaltyRule, as_of: date
) -> dict[str, Decimal]:
    """Total penalty accrued per installment up to and including ``as_of``."""
    result: dict[str, Decimal] = {item.item_id: ZERO for item in items}
    if rule.mode is PenaltyMode.OFF or rule.value <= 0 or not items:
        return result

    paid_by_item: dict[str, list[PaidEvent]] = defaultdict(list)
    for ev in events:
        paid_by_item[ev.item_id].append(ev)

    # Breakpoints where some unpaid amount may change.
    starts = {item.due_date + timedelta(days=1 + rule.grace_days) for item in items}
    starts |= {ev.on + timedelta(days=1) for ev in events}  # a payment counts from the next day
    end = as_of + timedelta(days=1)
    points = sorted(d for d in starts if d < end)
    if not points:
        return result
    points.append(end)

    def unpaid_at_start(item: PenaltyItem, day: date) -> Decimal:
        paid = sum((ev.amount for ev in paid_by_item[item.item_id] if ev.on < day), ZERO)
        return max(item.amount_due - paid, ZERO)

    raw: dict[str, Decimal] = defaultdict(lambda: ZERO)
    with localcontext() as ctx:
        ctx.prec = 40
        for seg_start, seg_end in zip(points, points[1:], strict=False):
            days = (seg_end - seg_start).days
            if days <= 0:
                continue
            overdue = [
                (item, unpaid_at_start(item, seg_start))
                for item in sorted(items, key=lambda it: it.due_date)
                if item.due_date + timedelta(days=rule.grace_days) < seg_start
            ]
            overdue = [(item, amt) for item, amt in overdue if amt > 0]
            if not overdue:
                continue
            if rule.mode is PenaltyMode.PER_DAY:
                raw[overdue[0][0].item_id] += rule.value * days
            else:
                daily = rule.value / Decimal(100) / 30
                for item, amt in overdue:
                    raw[item.item_id] += amt * daily * days
    for item_id, value in raw.items():
        result[item_id] = q2(value)
    return result
