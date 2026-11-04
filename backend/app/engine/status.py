"""Installment and loan status, derived at read time (PRD section 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from app.engine.money import ZERO


class ItemStatus(StrEnum):
    UPCOMING = "upcoming"
    DUE_TODAY = "due_today"
    PARTIALLY_PAID = "partially_paid"
    OVERDUE = "overdue"
    PAID = "paid"


class LoanStatus(StrEnum):
    ACTIVE = "active"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    CLOSED = "closed"
    WRITTEN_OFF = "written_off"


@dataclass(frozen=True)
class ItemState:
    item_id: str
    seq: int
    due_date: date
    principal_due: Decimal  # unpaid principal after waivers
    interest_due: Decimal  # unpaid interest after waivers
    penalty_due: Decimal  # unpaid penalty
    paid_any: bool

    @property
    def unpaid(self) -> Decimal:
        return self.principal_due + self.interest_due


def item_status(state: ItemState, today: date) -> ItemStatus:
    if state.unpaid <= 0 and state.penalty_due <= 0:
        return ItemStatus.PAID
    if state.due_date < today and state.unpaid > 0:
        return ItemStatus.OVERDUE
    if state.paid_any:
        return ItemStatus.PARTIALLY_PAID
    if state.due_date == today:
        return ItemStatus.DUE_TODAY
    if state.unpaid <= 0:  # only penalty left on a not-yet-due row cannot happen; be safe
        return ItemStatus.PAID
    return ItemStatus.UPCOMING


@dataclass(frozen=True)
class LoanSummary:
    status: LoanStatus
    overdue_days: int
    overdue_amount: Decimal
    overdue_installments: int
    due_today_amount: Decimal
    next_due_date: date | None
    next_due_amount: Decimal
    principal_outstanding: Decimal
    interest_outstanding: Decimal
    penalty_outstanding: Decimal
    total_outstanding: Decimal
    days_since_last_payment: int


def summarize(
    items: list[ItemState],
    today: date,
    disbursal_date: date,
    last_payment_date: date | None,
    stored_status: str,
    due_soon_days: int = 3,
) -> LoanSummary:
    ordered = sorted(items, key=lambda it: it.seq)
    overdue = [it for it in ordered if it.due_date < today and it.unpaid > 0]
    overdue_amount = sum((it.unpaid for it in overdue), ZERO) + sum(
        (it.penalty_due for it in ordered), ZERO
    )
    due_today = sum((it.unpaid + it.penalty_due for it in ordered if it.due_date == today), ZERO)
    upcoming = [it for it in ordered if it.due_date >= today and it.unpaid > 0]
    next_item = upcoming[0] if upcoming else None
    principal = sum((it.principal_due for it in ordered), ZERO)
    interest = sum((it.interest_due for it in ordered), ZERO)
    penalty = sum((it.penalty_due for it in ordered), ZERO)
    overdue_days = (today - overdue[0].due_date).days if overdue else 0
    since = (today - (last_payment_date or disbursal_date)).days

    if stored_status in (LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF):
        status = LoanStatus(stored_status)
    elif overdue:
        status = LoanStatus.OVERDUE
    elif next_item is not None and next_item.due_date <= today + timedelta(days=due_soon_days):
        status = LoanStatus.DUE_SOON
    else:
        status = LoanStatus.ACTIVE

    return LoanSummary(
        status=status,
        overdue_days=overdue_days,
        overdue_amount=overdue_amount,
        overdue_installments=len(overdue),
        due_today_amount=due_today,
        next_due_date=next_item.due_date if next_item else None,
        next_due_amount=(next_item.unpaid + next_item.penalty_due) if next_item else ZERO,
        principal_outstanding=principal,
        interest_outstanding=interest,
        penalty_outstanding=penalty,
        total_outstanding=principal + interest + penalty,
        days_since_last_payment=max(since, 0),
    )


def ageing_bucket(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "current"
    if overdue_days <= 7:
        return "1_7"
    if overdue_days <= 30:
        return "8_30"
    if overdue_days <= 60:
        return "31_60"
    if overdue_days <= 90:
        return "61_90"
    return "over_90"
