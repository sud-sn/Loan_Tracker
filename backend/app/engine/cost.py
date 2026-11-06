"""True cost of a loan: one rate that includes interest, charges and advance installments.

On the day the loan is given the borrower actually receives the principal minus everything
collected then (charges taken out of the loan, extra days' interest collected up front);
installments due that day (advance EMIs) are paid at once. Afterwards they pay each installment
on its due date. The true cost is the monthly rate at which the payments, discounted by date,
equal what was received: the internal rate of return, as used for an APR. Time is counted the
way the schedule charges interest: one period per installment (a month, a week or a day), plus
the extra or missing days of an odd first period. So a plain 2 % a month reducing loan with no
charges comes out at exactly 2 %, whether it is collected monthly, weekly or daily.

It is reported as % per month on a reducing basis and that x 12 as % a year, so it reads like
the rates the owner already quotes ("2 % a month reducing" = "24 % a year"). For example 12 %
flat a year over 3 years costs about 1.76 % a month, or 21 % a year, reducing.

This is a displayed estimate, rounded to 2 decimals, so it is solved in floating point; money
itself is never a float.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.engine.dates import add_months, one_period_after
from app.engine.money import q2
from app.engine.types import Frequency

# One installment period in months, as the schedule converts rates (a week = 7/30 of a month).
_PERIOD_MONTHS = {Frequency.MONTHLY: 1.0, Frequency.WEEKLY: 7 / 30, Frequency.DAILY: 1 / 30}
_PERIOD_DAYS = {Frequency.MONTHLY: 30, Frequency.WEEKLY: 7, Frequency.DAILY: 1}


@dataclass(frozen=True)
class TrueCost:
    monthly_percent: Decimal  # % per month, reducing basis, 2 decimals
    yearly_percent: Decimal  # the rounded monthly figure x 12


def true_cost(
    given_on: date, received: Decimal, payments: Sequence[tuple[date, Decimal]], frequency: Frequency
) -> TrueCost | None:
    """``received``: cash the borrower got on ``given_on``. ``payments``: the schedule's
    (due date, amount) in order; those due on ``given_on`` are advance installments."""
    if received <= 0:
        return None
    flows = _flows(given_on, payments, frequency)
    if not flows:
        return None
    cash = float(received)
    if sum(a for _, a in flows) <= cash:
        return TrueCost(q2(Decimal(0)), q2(Decimal(0)))

    def surplus(rate: float) -> float:  # value of the payments at ``rate`` minus what was received
        growth = math.log1p(rate)
        return sum(a * math.exp(-t * growth) for t, a in flows) - cash

    low, high = 0.0, 1.0
    while surplus(high) > 0:
        high *= 2
        if high > 1e4:  # over 1,000,000 % a month: the figures are not a real loan
            return None
    for _ in range(100):
        mid = (low + high) / 2
        if surplus(mid) > 0:
            low = mid
        else:
            high = mid
    period_months = _PERIOD_MONTHS.get(frequency, 1.0)
    monthly = q2(Decimal(repr((low + high) / 2 / period_months * 100)))
    return TrueCost(monthly, q2(monthly * 12))  # the yearly figure is always the shown monthly figure x 12


def _flows(given_on: date, payments: Sequence[tuple[date, Decimal]], frequency: Frequency) -> list[tuple[float, float]]:
    """(time in installment periods, amount) for each payment."""
    flows: list[tuple[float, float]] = []
    first: float | None = None
    regular = 0
    for due, amount in payments:
        if amount <= 0:
            continue
        if due <= given_on:
            t = 0.0
        elif frequency is Frequency.SINGLE:
            t = _months(given_on, due)
        else:
            if first is None:
                extra_days = (due - one_period_after(given_on, frequency)).days
                first = 1 + extra_days / _PERIOD_DAYS[frequency]
            t = first + regular
            regular += 1
        flows.append((t, float(amount)))
    return flows


def _months(start: date, end: date) -> float:
    """Whole calendar months from ``start`` to ``end``, plus leftover days as 1/30 of a month."""
    months = (end.year - start.year) * 12 + end.month - start.month
    while months > 0 and add_months(start, months) > end:
        months -= 1
    return months + (end - add_months(start, months)).days / 30
