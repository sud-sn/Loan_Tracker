"""Due and overdue lists (PRD section 6) — computed from the schedule and ledger at read time.

Lists work per loan using ``loan.next_unpaid_due`` (the oldest installment not fully paid, a
transactional cache of the ledger), so they stay fast at 200,000 loans. Amounts are then summed
from the installments of the loans on the page only.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import case, func, literal, select
from sqlalchemy.orm import Session

from app.engine import from_paise
from app.engine.money import ZERO
from app.engine.status import ageing_bucket
from app.models import Borrower, BusinessSettings, Loan, ScheduleItem
from app.services import ledger

ListName = Literal["today", "upcoming", "overdue", "long_unpaid"]

UNPAID = (
    ScheduleItem.principal_part + ScheduleItem.interest_part - ScheduleItem.paid_principal
    - ScheduleItem.paid_interest - ScheduleItem.waived_principal - ScheduleItem.waived_interest
)
ACTIVE = (Loan.status == "active", Loan.deleted_at.is_(None))


def _flagged(db: Session, today: date, borrower_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Borrowers with two or more overdue loans (PRD section 6), for the rows on screen."""
    if not borrower_ids:
        return set()
    return set(db.scalars(
        select(Loan.borrower_id)
        .where(*ACTIVE, Loan.borrower_id.in_(borrower_ids), Loan.next_unpaid_due < today)
        .group_by(Loan.borrower_id)
        .having(func.count() >= 2)
    ))


def _amounts(db: Session, loan_ids: list[uuid.UUID], *, until: date) -> dict[uuid.UUID, int]:
    """Unpaid principal + interest of installments due before ``until`` for some loans."""
    if not loan_ids:
        return {}
    rows = db.execute(
        select(ScheduleItem.loan_id, func.sum(UNPAID))
        .where(ScheduleItem.loan_id.in_(loan_ids), ~ScheduleItem.settled, ScheduleItem.due_date < until)
        .group_by(ScheduleItem.loan_id)
    )
    return {loan_id: int(amount) for loan_id, amount in rows}


def _row(loan: Loan, b: Borrower, *, amount: int, due_date: date | None, overdue_amount: int, today: date,
         flagged: set[uuid.UUID]) -> dict[str, Any]:
    oldest = loan.next_unpaid_due if loan.next_unpaid_due and loan.next_unpaid_due < today else None
    overdue_days = (today - oldest).days if oldest else 0
    return {
        "loan_id": loan.id, "loan_no": loan.loan_no, "borrower_id": b.id, "code": b.code, "name_en": b.name_en,
        "name_ta": b.name_ta, "phone": b.phone, "preferred_language": b.preferred_language,
        "amount_due": from_paise(amount), "due_date": due_date, "overdue_amount": from_paise(overdue_amount),
        "overdue_days": overdue_days, "bucket": ageing_bucket(overdue_days), "last_payment_on": loan.last_payment_on,
        "days_since_last_payment": (today - (loan.last_payment_on or loan.disbursal_date)).days,
        "multiple_overdue": b.id in flagged, "penalty_due": ZERO, "outstanding": from_paise(loan.outstanding),
    }


def _add_penalties(db: Session, rows: list[dict[str, Any]], today: date) -> None:
    """Unpaid penalty counts toward the overdue amount (PRD section 6), computed at read time."""
    ids = [r["loan_id"] for r in rows]
    if not ids:
        return
    loans = {ln.id: ln for ln in db.scalars(select(Loan).where(Loan.id.in_(ids), Loan.penalty_mode != "off"))}
    for r in rows:
        loan = loans.get(r["loan_id"])
        if loan is None:
            continue
        pen = sum(ledger.penalty_due(db, loan, ledger.load_items(db, loan.id), today).values(), Decimal("0"))
        r["penalty_due"] = pen
        r["overdue_amount"] += pen
        r["amount_due"] += pen


def list_dues(db: Session, business: BusinessSettings, which: ListName, today: date, *, sort: str = "overdue_days",
              page: int = 1, page_size: int = 50) -> tuple[list[dict[str, Any]], int]:
    offset = (page - 1) * page_size
    if which in ("today", "upcoming"):
        start, end = (today, today) if which == "today" else (today + timedelta(days=1),
                                                              today + timedelta(days=business.due_window_days))
        due = (
            select(ScheduleItem.loan_id.label("loan_id"), func.min(ScheduleItem.due_date).label("due"))
            .where(~ScheduleItem.settled, ScheduleItem.due_date.between(start, end))
            .group_by(ScheduleItem.loan_id)
            .subquery()
        )
        base = (
            select(Loan, Borrower, due.c.due, func.count().over().label("total"))
            .join(due, due.c.loan_id == Loan.id)
            .join(Borrower, Borrower.id == Loan.borrower_id)
            .where(*ACTIVE)
        )
        result = db.execute(base.order_by(due.c.due, Borrower.code).limit(page_size).offset(offset)).all()
        total = int(result[0].total) if result else 0
        ids = [r[0].id for r in result]
        # Amount due now = this window's installments plus anything already overdue.
        amounts = _amounts(db, ids, until=end + timedelta(days=1))
        overdue = _amounts(db, ids, until=today)
        flagged = _flagged(db, today, [r[1].id for r in result])
        rows = [
            _row(ln, b, amount=amounts.get(ln.id, 0), due_date=d, overdue_amount=overdue.get(ln.id, 0), today=today,
                 flagged=flagged)
            for ln, b, d, _ in result
        ]
    elif which == "overdue":
        base = (
            select(Loan, Borrower, func.count().over().label("total"))
            .join(Borrower, Borrower.id == Loan.borrower_id)
            .where(*ACTIVE, Loan.next_unpaid_due < today)
        )
        if sort == "overdue_amount":
            # Needs every overdue loan's amount: one aggregate over the unpaid past-due installments.
            per_loan = (
                select(ScheduleItem.loan_id.label("loan_id"), func.sum(UNPAID).label("amount"))
                .where(~ScheduleItem.settled, ScheduleItem.due_date < today)
                .group_by(ScheduleItem.loan_id)
                .subquery()
            )
            base = base.join(per_loan, per_loan.c.loan_id == Loan.id).order_by(per_loan.c.amount.desc(), Loan.loan_no)
        else:
            base = base.order_by(Loan.next_unpaid_due.asc(), Loan.loan_no)
        result = db.execute(base.limit(page_size).offset(offset)).all()
        total = int(result[0].total) if result else 0
        amounts = _amounts(db, [r[0].id for r in result], until=today)
        flagged = _flagged(db, today, [r[1].id for r in result])
        rows = [
            _row(ln, b, amount=amounts.get(ln.id, 0), due_date=ln.next_unpaid_due, overdue_amount=amounts.get(ln.id, 0),
                 today=today, flagged=flagged)
            for ln, b, _ in result
        ]
    else:  # long unpaid: no payment for more than X days, even if nothing is due yet
        cutoff = today - timedelta(days=business.long_unpaid_days)
        activity = func.coalesce(Loan.last_payment_on, Loan.disbursal_date)
        # Counted separately: a window count would make Postgres read every match before paging.
        total = int(db.scalar(select(func.count()).select_from(Loan).where(*ACTIVE, activity < cutoff)) or 0)
        base = (
            select(Loan, Borrower, literal(0).label("total"))
            .join(Borrower, Borrower.id == Loan.borrower_id)
            .where(*ACTIVE, activity < cutoff)
        )
        result = db.execute(base.order_by(activity.asc(), Loan.loan_no).limit(page_size).offset(offset)).all()
        overdue = _amounts(db, [r[0].id for r in result], until=today)
        flagged = _flagged(db, today, [r[1].id for r in result])
        rows = [
            _row(ln, b, amount=overdue.get(ln.id, 0), due_date=None, overdue_amount=overdue.get(ln.id, 0), today=today,
                 flagged=flagged)
            for ln, b, _ in result
        ]
    _add_penalties(db, rows, today)
    return rows, total


def counts(db: Session, business: BusinessSettings, today: date) -> dict[str, Any]:
    def window(start: date, end: date) -> tuple[int, int]:
        row = db.execute(
            select(func.count(func.distinct(ScheduleItem.loan_id)), func.coalesce(func.sum(UNPAID), 0))
            .join(Loan, Loan.id == ScheduleItem.loan_id)
            .where(*ACTIVE, ~ScheduleItem.settled, ScheduleItem.due_date.between(start, end))
        ).one()
        return int(row[0]), int(row[1])

    due_today = window(today, today)
    upcoming = window(today + timedelta(days=1), today + timedelta(days=business.due_window_days))
    cutoff = today - timedelta(days=business.long_unpaid_days)
    long_unpaid = db.scalar(
        select(func.count()).select_from(Loan)
        .where(*ACTIVE, func.coalesce(Loan.last_payment_on, Loan.disbursal_date) < cutoff)
    ) or 0
    # Ageing by each overdue loan's oldest unpaid installment, with its overdue amount.
    days = today - Loan.next_unpaid_due
    bucket = case((days <= 7, "1_7"), (days <= 30, "8_30"), (days <= 60, "31_60"), (days <= 90, "61_90"),
                  else_="over_90")
    per_loan = (
        select(ScheduleItem.loan_id.label("loan_id"), func.sum(UNPAID).label("amount"))
        .where(~ScheduleItem.settled, ScheduleItem.due_date < today)
        .group_by(ScheduleItem.loan_id)
        .subquery()
    )
    ageing = dict.fromkeys(("1_7", "8_30", "31_60", "61_90", "over_90"), (0, 0))
    for name, n, amount in db.execute(
        select(bucket, func.count(), func.coalesce(func.sum(per_loan.c.amount), 0))
        .select_from(Loan).join(per_loan, per_loan.c.loan_id == Loan.id)
        .where(*ACTIVE, Loan.next_unpaid_due < today)
        .group_by(bucket)
    ):
        ageing[name] = (int(n), int(amount))
    return {
        "due_today": {"count": due_today[0], "amount": from_paise(due_today[1])},
        "upcoming": {"count": upcoming[0], "amount": from_paise(upcoming[1])},
        "overdue": {"count": sum(v[0] for v in ageing.values()), "amount": from_paise(sum(v[1] for v in ageing.values()))},
        "long_unpaid": {"count": int(long_unpaid)},
        "ageing": {k: {"count": v[0], "amount": from_paise(v[1])} for k, v in ageing.items()},
    }
