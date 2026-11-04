"""Read-time loan state from the schedule and the ledger (PRD section 6 and 11).

Everything here is derived from schedule_item, payment_allocation and loan_adjustment. The
``paid_*``/``waived_*`` columns on schedule_item are a transactional cache that
``rebuild_item_cache`` can recompute at any time.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.engine.money import ZERO, from_paise
from app.engine.penalty import PaidEvent, PenaltyItem, PenaltyMode, PenaltyRule, accrued_penalty
from app.engine.status import ItemState, LoanSummary, summarize
from app.models import Loan, LoanAdjustment, Payment, PaymentAllocation, ScheduleItem


def load_items(db: Session, loan_id: uuid.UUID, *, lock: bool = False) -> list[ScheduleItem]:
    stmt = select(ScheduleItem).where(ScheduleItem.loan_id == loan_id).order_by(ScheduleItem.seq)
    if lock:
        stmt = stmt.with_for_update()
    return list(db.scalars(stmt))


def lock_loan(db: Session, loan_id: uuid.UUID) -> Loan | None:
    """Row lock on the loan so two simultaneous payments cannot double-allocate (PRD section 13)."""
    return db.scalars(select(Loan).where(Loan.id == loan_id, Loan.deleted_at.is_(None)).with_for_update()).first()


def penalty_rule(loan: Loan) -> PenaltyRule:
    return PenaltyRule(PenaltyMode(loan.penalty_mode), Decimal(loan.penalty_value), loan.penalty_grace_days)


def paid_events(db: Session, loan_id: uuid.UUID) -> list[PaidEvent]:
    """Principal + interest paid per installment, by payment date, ignoring reversed payments."""
    reversal = aliased(Payment)
    rows = db.execute(
        select(PaymentAllocation.schedule_item_id, Payment.paid_on,
               PaymentAllocation.principal_part + PaymentAllocation.interest_part)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .outerjoin(reversal, reversal.reversed_of_id == Payment.id)
        .where(Payment.loan_id == loan_id, Payment.kind != "reversal", reversal.id.is_(None))
    ).all()
    return [PaidEvent(str(item_id), on, from_paise(amount)) for item_id, on, amount in rows]


def penalty_due(db: Session, loan: Loan, items: list[ScheduleItem], as_of: date) -> dict[uuid.UUID, Decimal]:
    """Unpaid penalty per installment as of a date (accrued - paid - waived), never below zero."""
    if loan.penalty_mode == PenaltyMode.OFF:
        return {it.id: ZERO for it in items}
    accrued = accrued_penalty(
        [PenaltyItem(str(it.id), it.due_date, from_paise(it.installment - it.waived_principal - it.waived_interest))
         for it in items],
        paid_events(db, loan.id),
        penalty_rule(loan),
        as_of,
    )
    return {
        it.id: max(accrued[str(it.id)] - from_paise(it.paid_penalty + it.waived_penalty), ZERO) for it in items
    }


def item_states(
    db: Session, loan: Loan, items: list[ScheduleItem], today: date
) -> tuple[list[ItemState], dict[uuid.UUID, Decimal]]:
    pen = penalty_due(db, loan, items, today) if loan.status == "active" else {it.id: ZERO for it in items}
    states = [
        ItemState(
            item_id=str(it.id), seq=it.seq, due_date=it.due_date,
            principal_due=from_paise(it.principal_due), interest_due=from_paise(it.interest_due),
            penalty_due=pen[it.id],
            paid_any=(it.paid_principal + it.paid_interest + it.paid_penalty) > 0,
        )
        for it in items
    ]
    return states, pen


def summary(db: Session, loan: Loan, items: list[ScheduleItem], today: date, due_soon_days: int) -> LoanSummary:
    states, _ = item_states(db, loan, items, today)
    return summarize(states, today, loan.disbursal_date, loan.last_payment_on, loan.status, due_soon_days)


def apply_to_item(item: ScheduleItem, penalty: int, interest: int, principal: int) -> None:
    item.paid_penalty += penalty
    item.paid_interest += interest
    item.paid_principal += principal
    item.settled = item.principal_due <= 0 and item.interest_due <= 0


def waive_on_item(item: ScheduleItem, penalty: int, interest: int, principal: int) -> None:
    item.waived_penalty += penalty
    item.waived_interest += interest
    item.waived_principal += principal
    item.settled = item.principal_due <= 0 and item.interest_due <= 0


def refresh_loan_cache(loan: Loan, items: list[ScheduleItem]) -> None:
    loan.outstanding = sum(max(it.principal_due + it.interest_due, 0) for it in items)


def last_payment_on(db: Session, loan_id: uuid.UUID) -> date | None:
    reversal = aliased(Payment)
    return db.scalar(
        select(func.max(Payment.paid_on))
        .outerjoin(reversal, reversal.reversed_of_id == Payment.id)
        .where(Payment.loan_id == loan_id, Payment.kind != "reversal", reversal.id.is_(None))
    )


def rebuild_item_cache(db: Session, loan_id: uuid.UUID, *, fix: bool = True) -> list[str]:
    """Recompute paid/waived columns from the ledger. Returns a description of any drift."""
    items = load_items(db, loan_id, lock=fix)
    paid: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])
    for item_id, pen, intr, prin in db.execute(
        select(PaymentAllocation.schedule_item_id, func.sum(PaymentAllocation.penalty_part),
               func.sum(PaymentAllocation.interest_part), func.sum(PaymentAllocation.principal_part))
        .join(ScheduleItem, ScheduleItem.id == PaymentAllocation.schedule_item_id)
        .where(ScheduleItem.loan_id == loan_id)
        .group_by(PaymentAllocation.schedule_item_id)
    ):
        paid[item_id] = [int(pen), int(intr), int(prin)]
    waived: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])
    for item_id, pen, intr, prin in db.execute(
        select(LoanAdjustment.schedule_item_id, func.sum(LoanAdjustment.penalty_part),
               func.sum(LoanAdjustment.interest_part), func.sum(LoanAdjustment.principal_part))
        .where(LoanAdjustment.loan_id == loan_id)
        .group_by(LoanAdjustment.schedule_item_id)
    ):
        waived[item_id] = [int(pen), int(intr), int(prin)]
    drift: list[str] = []
    loan = db.get(Loan, loan_id)
    for it in items:
        want = (*paid[it.id], *waived[it.id])
        have = (it.paid_penalty, it.paid_interest, it.paid_principal, it.waived_penalty, it.waived_interest,
                it.waived_principal)
        if want != have:
            drift.append(f"loan {loan_id} item {it.seq}: cached {have} != ledger {want}")
            if fix:
                (it.paid_penalty, it.paid_interest, it.paid_principal, it.waived_penalty, it.waived_interest,
                 it.waived_principal) = want
        settled = it.principal_due <= 0 and it.interest_due <= 0
        if settled != it.settled:
            drift.append(f"loan {loan_id} item {it.seq}: settled flag {it.settled} != {settled}")
            if fix:
                it.settled = settled
    if loan is not None:
        want_outstanding = sum(max(it.principal_due + it.interest_due, 0) for it in items)
        if loan.outstanding != want_outstanding:
            drift.append(f"loan {loan_id}: outstanding cache {loan.outstanding} != {want_outstanding}")
            if fix:
                loan.outstanding = want_outstanding
        want_last = last_payment_on(db, loan_id)
        if loan.last_payment_on != want_last:
            drift.append(f"loan {loan_id}: last_payment_on {loan.last_payment_on} != {want_last}")
            if fix:
                loan.last_payment_on = want_last
    return drift
