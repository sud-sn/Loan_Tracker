"""Due and overdue lists (PRD section 6) — computed from the schedule and ledger at read time."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, literal_column, select
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


def _multi_overdue_borrowers(db: Session, today: date) -> set[Any]:
    sub = (
        select(Loan.borrower_id, Loan.id)
        .join(ScheduleItem, ScheduleItem.loan_id == Loan.id)
        .where(Loan.status == "active", Loan.deleted_at.is_(None), ~ScheduleItem.settled, ScheduleItem.due_date < today)
        .distinct()
        .subquery()
    )
    return set(db.scalars(select(sub.c.borrower_id).group_by(sub.c.borrower_id).having(func.count() >= 2)))


def _row(loan: Loan, b: Borrower, *, amount: int, due_date: date | None, oldest_overdue: date | None,
         overdue_amount: int, today: date, flagged: set[Any]) -> dict[str, Any]:
    overdue_days = (today - oldest_overdue).days if oldest_overdue else 0
    return {
        "loan_id": loan.id, "loan_no": loan.loan_no, "borrower_id": b.id, "code": b.code, "name_en": b.name_en,
        "name_ta": b.name_ta, "phone": b.phone, "preferred_language": b.preferred_language,
        "amount_due": from_paise(amount), "due_date": due_date, "overdue_amount": from_paise(overdue_amount),
        "overdue_days": overdue_days, "bucket": ageing_bucket(overdue_days), "last_payment_on": loan.last_payment_on,
        "days_since_last_payment": (today - (loan.last_payment_on or loan.disbursal_date)).days,
        "multiple_overdue": b.id in flagged, "penalty_due": ZERO,
    }


def _overdue_by_loan(db: Session, today: date, loan_ids: list[Any] | None = None) -> dict[Any, tuple[int, date]]:
    stmt = (
        select(ScheduleItem.loan_id, func.sum(UNPAID), func.min(ScheduleItem.due_date))
        .join(Loan, Loan.id == ScheduleItem.loan_id)
        .where(~ScheduleItem.settled, ScheduleItem.due_date < today, Loan.status == "active", Loan.deleted_at.is_(None))
        .group_by(ScheduleItem.loan_id)
    )
    if loan_ids is not None:
        stmt = stmt.where(ScheduleItem.loan_id.in_(loan_ids))
    return {loan_id: (int(amount), oldest) for loan_id, amount, oldest in db.execute(stmt)}


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


def list_dues(db: Session, business: BusinessSettings, which: ListName, today: date, *, sort: str = "overdue_days",
              page: int = 1, page_size: int = 50) -> tuple[list[dict[str, Any]], int]:
    flagged = _multi_overdue_borrowers(db, today)
    active = (Loan.status == "active", Loan.deleted_at.is_(None))
    if which in ("today", "upcoming"):
        start, end = (today, today) if which == "today" else (today + timedelta(days=1),
                                                              today + timedelta(days=business.due_window_days))
        base = (
            select(Loan, Borrower, func.sum(UNPAID).label("amount"), func.min(ScheduleItem.due_date).label("due"))
            .join(ScheduleItem, ScheduleItem.loan_id == Loan.id)
            .join(Borrower, Borrower.id == Loan.borrower_id)
            .where(*active, ~ScheduleItem.settled, ScheduleItem.due_date.between(start, end))
            .group_by(Loan.id, Borrower.id)
        )
        total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
        due_rows = db.execute(base.order_by(literal_column("due"), Borrower.code).limit(page_size)
                              .offset((page - 1) * page_size)).all()
        overdue = _overdue_by_loan(db, today, [r[0].id for r in due_rows])
        rows = [
            _row(ln, b, amount=int(amount) + overdue.get(ln.id, (0, None))[0], due_date=due,
                 oldest_overdue=overdue.get(ln.id, (0, None))[1], overdue_amount=overdue.get(ln.id, (0, None))[0],
                 today=today, flagged=flagged)
            for ln, b, amount, due in due_rows
        ]
    elif which == "overdue":
        per_loan = (
            select(ScheduleItem.loan_id.label("loan_id"), func.sum(UNPAID).label("amount"),
                   func.min(ScheduleItem.due_date).label("oldest"))
            .join(Loan, Loan.id == ScheduleItem.loan_id)
            .where(*active, ~ScheduleItem.settled, ScheduleItem.due_date < today)
            .group_by(ScheduleItem.loan_id)
            .subquery()
        )
        od_base = (
            select(Loan, Borrower, per_loan.c.amount, per_loan.c.oldest)
            .join(per_loan, per_loan.c.loan_id == Loan.id)
            .join(Borrower, Borrower.id == Loan.borrower_id)
        )
        total = db.scalar(select(func.count()).select_from(per_loan)) or 0
        order = per_loan.c.amount.desc() if sort == "overdue_amount" else per_loan.c.oldest.asc()
        od_rows = db.execute(od_base.order_by(order, Loan.loan_no).limit(page_size).offset((page - 1) * page_size)).all()
        rows = [
            _row(ln, b, amount=int(amount), due_date=oldest, oldest_overdue=oldest, overdue_amount=int(amount),
                 today=today, flagged=flagged)
            for ln, b, amount, oldest in od_rows
        ]
    else:  # long unpaid: no payment for more than X days, even if nothing is due yet
        cutoff = today - timedelta(days=business.long_unpaid_days)
        activity = func.coalesce(Loan.last_payment_on, Loan.disbursal_date)
        lu_base = (
            select(Loan, Borrower)
            .join(Borrower, Borrower.id == Loan.borrower_id)
            .where(*active, activity < cutoff)
        )
        total = db.scalar(select(func.count()).select_from(lu_base.subquery())) or 0
        lu_rows = db.execute(lu_base.order_by(activity.asc(), Loan.loan_no).limit(page_size)
                             .offset((page - 1) * page_size)).all()
        overdue = _overdue_by_loan(db, today, [r[0].id for r in lu_rows])
        rows = [
            _row(ln, b, amount=overdue.get(ln.id, (0, None))[0], due_date=None,
                 oldest_overdue=overdue.get(ln.id, (0, None))[1], overdue_amount=overdue.get(ln.id, (0, None))[0],
                 today=today, flagged=flagged)
            for ln, b in lu_rows
        ]
    _add_penalties(db, rows, today)
    return rows, total


def counts(db: Session, business: BusinessSettings, today: date) -> dict[str, Any]:
    active = (Loan.status == "active", Loan.deleted_at.is_(None))

    def agg(where: Any) -> tuple[int, int]:
        row = db.execute(
            select(func.count(func.distinct(ScheduleItem.loan_id)), func.coalesce(func.sum(UNPAID), 0))
            .join(Loan, Loan.id == ScheduleItem.loan_id)
            .where(*active, ~ScheduleItem.settled, where)
        ).one()
        return int(row[0]), int(row[1])

    due_today = agg(ScheduleItem.due_date == today)
    overdue = agg(ScheduleItem.due_date < today)
    upcoming = agg(ScheduleItem.due_date.between(today + timedelta(days=1), today + timedelta(days=business.due_window_days)))
    cutoff = today - timedelta(days=business.long_unpaid_days)
    long_unpaid = db.scalar(
        select(func.count()).select_from(Loan)
        .where(*active, func.coalesce(Loan.last_payment_on, Loan.disbursal_date) < cutoff)
    ) or 0
    ageing = dict.fromkeys(("1_7", "8_30", "31_60", "61_90", "over_90"), (0, 0))
    for oldest, amount in db.execute(
        select(func.min(ScheduleItem.due_date), func.sum(UNPAID))
        .join(Loan, Loan.id == ScheduleItem.loan_id)
        .where(*active, ~ScheduleItem.settled, ScheduleItem.due_date < today)
        .group_by(ScheduleItem.loan_id)
    ):
        bucket = ageing_bucket((today - oldest).days)
        n, total = ageing[bucket]
        ageing[bucket] = (n + 1, total + int(amount))
    return {
        "due_today": {"count": due_today[0], "amount": from_paise(due_today[1])},
        "upcoming": {"count": upcoming[0], "amount": from_paise(upcoming[1])},
        "overdue": {"count": overdue[0], "amount": from_paise(overdue[1])},
        "long_unpaid": {"count": int(long_unpaid)},
        "ageing": {k: {"count": v[0], "amount": from_paise(v[1])} for k, v in ageing.items()},
    }

