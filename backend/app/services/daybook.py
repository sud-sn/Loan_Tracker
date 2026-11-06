"""Home page: today's log, or daybook (PRD section 7).

Built from the ``daily_log`` view (payments in, loans out, charges collected when a loan is given,
hand-typed cash entries). The cash
balance runs from the start date and opening balance in Settings; earlier entries are history
only. closing = opening + in - out, always.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, Integer, String, case, column, func, select, table, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from app.engine import from_paise
from app.models import (
    Borrower,
    BusinessSettings,
    CashEntry,
    Category,
    Loan,
    LoanCharge,
    Payment,
    PaymentAllocation,
    Refund,
)

# How a charge collected when a loan is given is named on the daily log and in exports.
CHARGE_NAMES = {
    "processing_fee": ("Processing fee", "செயலாக்கக் கட்டணம்"),
    "document_charges": ("Document charges", "ஆவணக் கட்டணம்"),
    "rto_stamp": ("RTO / stamp charges", "ஆர்.டி.ஓ / முத்திரைக் கட்டணம்"),
    "insurance": ("Insurance", "காப்பீடு"),
    "odd_period_interest": ("Interest for extra days", "கூடுதல் நாட்களுக்கான வட்டி"),
}

daily_log = table(
    "daily_log",
    column("entry_date", Date), column("direction", String), column("source_type", String),
    column("source_id", UUID(as_uuid=True)), column("amount", Integer), column("mode", String),
    column("loan_id", UUID(as_uuid=True)),
)


def balance_before(db: Session, business: BusinessSettings, day: date) -> int | None:
    start = business.balance_start_date
    if start is None or day < start:
        return None
    net = db.scalar(
        select(func.coalesce(func.sum(
            text("CASE WHEN direction = 'in' THEN amount ELSE -amount END")), 0))
        .select_from(daily_log)
        .where(daily_log.c.entry_date >= start, daily_log.c.entry_date < day)
    )
    return business.opening_balance + int(net or 0)


def totals(db: Session, start: date, end: date) -> dict[str, int]:
    rows = db.execute(
        select(daily_log.c.direction, func.coalesce(func.sum(daily_log.c.amount), 0))
        .where(daily_log.c.entry_date.between(start, end))
        .group_by(daily_log.c.direction)
    ).all()
    got = {d: int(a) for d, a in rows}
    return {"in": got.get("in", 0), "out": got.get("out", 0)}


def by_mode(db: Session, day: date) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"in": 0, "out": 0})
    for mode, direction, amount in db.execute(
        select(daily_log.c.mode, daily_log.c.direction, func.sum(daily_log.c.amount))
        .where(daily_log.c.entry_date == day)
        .group_by(daily_log.c.mode, daily_log.c.direction)
    ):
        out[mode][direction] = int(amount)
    return {m: {"in": from_paise(v["in"]), "out": from_paise(v["out"])} for m, v in out.items()}


def entries(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    """Every line of the log in the range, with what it came from."""
    out: list[dict[str, Any]] = []
    payments = db.execute(
        select(Payment, Loan.loan_no, Loan.id, Borrower.code, Borrower.name_en, Borrower.name_ta)
        .join(Loan, Loan.id == Payment.loan_id).join(Borrower, Borrower.id == Loan.borrower_id)
        .where(Payment.paid_on.between(start, end))
        .order_by(Payment.paid_on, Payment.created_at)
    ).all()
    splits: dict[uuid.UUID, tuple[int, int, int]] = {}
    if payments:
        for pid, pen, intr, prin in db.execute(
            select(PaymentAllocation.payment_id, func.sum(PaymentAllocation.penalty_part),
                   func.sum(PaymentAllocation.interest_part), func.sum(PaymentAllocation.principal_part))
            .where(PaymentAllocation.payment_id.in_([p.id for p, *_ in payments]))
            .group_by(PaymentAllocation.payment_id)
        ):
            splits[pid] = (int(pen), int(intr), int(prin))
    for p, loan_no, loan_id, code, name_en, name_ta in payments:
        pen, intr, prin = splits.get(p.id, (0, 0, 0))
        sign = -1 if p.kind == "reversal" else 1
        out.append({
            "date": p.paid_on, "direction": "in", "source_type": "payment", "source_id": p.id, "kind": p.kind,
            "amount": from_paise(sign * p.amount), "mode": p.mode, "loan_id": loan_id, "loan_no": loan_no,
            "code": code, "name_en": name_en, "name_ta": name_ta, "receipt_no": p.receipt_no,
            "principal": from_paise(prin), "interest": from_paise(intr), "penalty": from_paise(pen),
            "category_en": None, "category_ta": None, "note": p.note, "created_at": p.created_at,
        })
    for ln, code, name_en, name_ta in db.execute(
        select(Loan, Borrower.code, Borrower.name_en, Borrower.name_ta)
        .join(Borrower, Borrower.id == Loan.borrower_id)
        .where(Loan.disbursal_date.between(start, end), Loan.deleted_at.is_(None))
        .order_by(Loan.disbursal_date, Loan.created_at)
    ):
        out.append({
            "date": ln.disbursal_date, "direction": "out", "source_type": "loan", "source_id": ln.id, "kind": "loan",
            "amount": from_paise(ln.principal), "mode": ln.disbursal_mode, "loan_id": ln.id, "loan_no": ln.loan_no,
            "code": code, "name_en": name_en, "name_ta": name_ta, "receipt_no": None, "principal": None,
            "interest": None, "penalty": None, "category_en": None, "category_ta": None, "note": ln.purpose,
            "created_at": ln.created_at,
        })
    # Charges collected when a loan is given (fees taken out or added, extra days' interest).
    for ch, ln, code, name_en, name_ta in db.execute(
        select(LoanCharge, Loan, Borrower.code, Borrower.name_en, Borrower.name_ta)
        .join(Loan, Loan.id == LoanCharge.loan_id).join(Borrower, Borrower.id == Loan.borrower_id)
        .where(Loan.disbursal_date.between(start, end), Loan.deleted_at.is_(None))
        .order_by(Loan.disbursal_date, LoanCharge.created_at)
    ):
        en, ta = CHARGE_NAMES.get(ch.kind, (ch.label or "", ch.label or ""))
        out.append({
            "date": ln.disbursal_date, "direction": "in", "source_type": "loan_charge", "source_id": ch.id,
            "kind": "charge", "amount": from_paise(ch.amount), "mode": ln.disbursal_mode, "loan_id": ln.id,
            "loan_no": ln.loan_no, "code": code, "name_en": name_en, "name_ta": name_ta, "receipt_no": None,
            "principal": None, "interest": None, "penalty": None, "category_en": en, "category_ta": ta,
            "note": ch.label if ch.kind != "other" else None, "treatment": ch.treatment, "created_at": ch.created_at,
        })
    # A sale surplus: received from the buyer and given back to the borrower (both lines show).
    for r, ln, code, name_en, name_ta in db.execute(
        select(Refund, Loan, Borrower.code, Borrower.name_en, Borrower.name_ta)
        .join(Loan, Loan.id == Refund.loan_id).join(Borrower, Borrower.id == Loan.borrower_id)
        .where(Refund.refunded_on.between(start, end)).order_by(Refund.refunded_on, Refund.created_at)
    ):
        for direction, kind in (("in", "sale_surplus"), ("out", "refund")):
            out.append({
                "date": r.refunded_on, "direction": direction, "source_type": kind, "source_id": r.id, "kind": kind,
                "amount": from_paise(r.amount), "mode": r.mode, "loan_id": ln.id, "loan_no": ln.loan_no, "code": code,
                "name_en": name_en, "name_ta": name_ta, "receipt_no": None, "principal": None, "interest": None,
                "penalty": None, "category_en": None, "category_ta": None, "note": r.reason, "created_at": r.created_at,
            })
    for c, cat in db.execute(
        select(CashEntry, Category).join(Category, Category.id == CashEntry.category_id)
        .where(CashEntry.entry_date.between(start, end), CashEntry.deleted_at.is_(None))
        .order_by(CashEntry.entry_date, CashEntry.created_at)
    ):
        out.append({
            "date": c.entry_date, "direction": c.direction, "source_type": "cash_entry", "source_id": c.id,
            "kind": "income" if c.direction == "in" else "expense", "amount": from_paise(c.amount), "mode": c.mode,
            "loan_id": None, "loan_no": None, "code": None, "name_en": None, "name_ta": None, "receipt_no": None,
            "principal": None, "interest": None, "penalty": None, "category_en": cat.name_en,
            "category_ta": cat.name_ta, "note": c.note, "created_at": c.created_at, "version": c.version,
        })
    out.sort(key=lambda e: (e["date"], e["created_at"]))
    return out


def day(db: Session, business: BusinessSettings, on: date) -> dict[str, Any]:
    opening = balance_before(db, business, on)
    t = totals(db, on, on)
    week_start = on - timedelta(days=on.weekday())
    month_start = on.replace(day=1)
    week, month = totals(db, week_start, on), totals(db, month_start, on)
    lines = entries(db, on, on)
    return {
        "date": on,
        "tracked": opening is not None,
        "balance_start_date": business.balance_start_date,
        "opening_balance": from_paise(opening) if opening is not None else None,
        "money_in": from_paise(t["in"]),
        "money_out": from_paise(t["out"]),
        "net": from_paise(t["in"] - t["out"]),
        "closing_balance": from_paise(opening + t["in"] - t["out"]) if opening is not None else None,
        "by_mode": by_mode(db, on),
        "week": {"start": week_start, "in": from_paise(week["in"]), "out": from_paise(week["out"]),
                 "net": from_paise(week["in"] - week["out"])},
        "month": {"start": month_start, "in": from_paise(month["in"]), "out": from_paise(month["out"]),
                  "net": from_paise(month["in"] - month["out"])},
        "entries_in": [e for e in lines if e["direction"] == "in"],
        "entries_out": [e for e in lines if e["direction"] == "out"],
    }


def reconcile(db: Session, start: date, end: date) -> dict[str, int]:
    """The view must always match the source tables (PRD section 11); used by a test and the nightly job."""
    view = totals(db, start, end)
    pay_in = db.scalar(
        select(func.coalesce(func.sum(case((Payment.kind == "reversal", -Payment.amount), else_=Payment.amount)), 0))
        .where(Payment.paid_on.between(start, end))
    ) or 0
    cash_in = db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(
        CashEntry.entry_date.between(start, end), CashEntry.direction == "in", CashEntry.deleted_at.is_(None))) or 0
    cash_out = db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(
        CashEntry.entry_date.between(start, end), CashEntry.direction == "out", CashEntry.deleted_at.is_(None))) or 0
    loans_out = db.scalar(select(func.coalesce(func.sum(Loan.principal), 0)).where(
        Loan.disbursal_date.between(start, end), Loan.deleted_at.is_(None))) or 0
    return {"view_in": view["in"], "source_in": int(pay_in) + int(cash_in),
            "view_out": view["out"], "source_out": int(loans_out) + int(cash_out)}

