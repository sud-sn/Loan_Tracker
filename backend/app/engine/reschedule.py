"""New installments after a part-prepayment (Phase 2).

When the borrower pays extra, the extra reduces the principal. The installments not yet due are
replaced by new ones on the same due dates, either

* ``REDUCE_EMI``: the same number of installments, each smaller, or
* ``REDUCE_TERM``: the same installment amount, so the loan finishes sooner.

Interest of the period in which the extra was paid is split by days: the old figure for the days
before the payment, the new (lower) figure for the days after. Everything else follows the loan's
own method, rounding and the rules in ``schedule.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from app.engine.errors import EngineError
from app.engine.money import CENT, ZERO, q2
from app.engine.schedule import (
    _fill_fixed_principal,
    _fixed_amount_parts,
    _flat_parts_ext,
    _interest_only_parts,
    _reducing_parts_ext,
)
from app.engine.types import FixedStyle


class RescheduleMode(StrEnum):
    REDUCE_EMI = "reduce_emi"
    REDUCE_TERM = "reduce_term"


class Style(StrEnum):
    REDUCING = "reducing"
    FLAT = "flat"
    INTEREST_ONLY = "interest_only"


@dataclass(frozen=True)
class RescheduleResult:
    parts: tuple[tuple[Decimal, Decimal], ...]  # (principal, interest) per new installment
    dates: tuple[date, ...]
    installment: Decimal  # the regular new installment
    total_interest: Decimal


def reschedule(
    *, balance: Decimal, rate: Decimal, style: Style, mode: RescheduleMode, dates: list[date],
    old_installment: Decimal, old_first_interest: Decimal, period_start: date, paid_on: date,
    step: Decimal = CENT,
) -> RescheduleResult:
    """``balance``: principal still owed after the extra payment. ``rate``: per installment period,
    as a fraction. ``dates``: due dates of the installments being replaced (oldest first).
    ``old_first_interest``: interest the first replaced installment carried. ``period_start``:
    the due date before it (or the day the loan was given)."""
    if balance <= 0:
        raise EngineError("PREPAY_USE_SETTLEMENT")
    if not dates:
        raise EngineError("NOTHING_TO_RESCHEDULE")
    n = len(dates)
    with localcontext() as ctx:
        ctx.prec = 40
        if style is Style.INTEREST_ONLY:
            if mode is RescheduleMode.REDUCE_TERM:
                raise EngineError("RESCHEDULE_MODE_NOT_FOR_METHOD")
            parts = _interest_only_parts(balance, rate, n)
        elif mode is RescheduleMode.REDUCE_EMI:
            parts = (_reducing_parts_ext(balance, rate, n, 0, step) if style is Style.REDUCING
                     else _flat_parts_ext(balance, rate, n, step))[0]
        elif style is Style.REDUCING:
            parts = _fixed_amount_parts(balance, rate, old_installment, FixedStyle.REDUCING)
        else:
            interest_each = q2(balance * rate)
            if old_installment <= interest_each:
                raise EngineError("INSTALLMENT_TOO_SMALL", minimum=str(interest_each + CENT))
            parts = _fill_fixed_principal(balance, old_installment - interest_each, interest_each)
        if len(parts) > n:  # pragma: no cover - a smaller balance never needs more installments
            raise EngineError("TERM_TOO_LONG", max=n)
        parts = list(parts)
        # The period the extra was paid in: old interest for the days before, new after.
        span = max((dates[0] - period_start).days, 1)
        elapsed = min(max((paid_on - period_start).days, 0), span)
        p0, i0 = parts[0]
        first = q2(old_first_interest * elapsed / span + i0 * (span - elapsed) / span)
        parts[0] = (p0, max(first, ZERO))
        if parts[0][0] + parts[0][1] <= 0:
            raise EngineError("SCHEDULE_ROW_EMPTY", seq=1)
    installments = [p + i for p, i in parts]
    regular = installments[1] if len(installments) > 2 else installments[0]
    return RescheduleResult(
        parts=tuple(parts), dates=tuple(dates[: len(parts)]), installment=regular,
        total_interest=sum((i for _, i in parts), ZERO),
    )
