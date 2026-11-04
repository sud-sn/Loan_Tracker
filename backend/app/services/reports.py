"""Reports and dashboard cards (PRD section 7). All derived from the ledger."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Literal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.core import i18n
from app.engine import from_paise
from app.models import BusinessSettings, Loan, Payment, PaymentAllocation
from app.repositories import borrowers as borrower_repo
from app.services import dues, pdf


def collections(db: Session, start: date, end: date, group: Literal["day", "month"]) -> list[dict[str, Any]]:
    period = Payment.paid_on if group == "day" else cast(func.date_trunc("month", Payment.paid_on), Date)
    rows = db.execute(
        select(
            period.label("period"),
            func.count(func.distinct(Payment.id)).filter(Payment.kind != "reversal"),
            func.coalesce(func.sum(PaymentAllocation.principal_part), 0),
            func.coalesce(func.sum(PaymentAllocation.interest_part), 0),
            func.coalesce(func.sum(PaymentAllocation.penalty_part), 0),
        )
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .where(Payment.paid_on.between(start, end))
        .group_by(period)
        .order_by(period)
    ).all()
    return [
        {"period": p, "count": int(n), "principal": from_paise(int(pr)), "interest": from_paise(int(i)),
         "penalty": from_paise(int(pe)), "total": from_paise(int(pr) + int(i) + int(pe))}
        for p, n, pr, i, pe in rows
    ]


def interest_earned(db: Session, start: date | None, end: date) -> dict[str, Any]:
    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.interest_part), 0),
               func.coalesce(func.sum(PaymentAllocation.penalty_part), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.paid_on <= end)
    )
    if start:
        stmt = stmt.where(Payment.paid_on >= start)
    interest, penalty = db.execute(stmt).one()
    return {"interest": from_paise(int(interest)), "penalty": from_paise(int(penalty))}


def outstanding_by_borrower(db: Session, today: date, limit: int = 5000) -> list[dict[str, Any]]:
    stmt = borrower_repo.list_query(today, status=None, has_overdue=None, has_active_loan=True, sort="outstanding",
                                    descending=True).limit(limit)
    return [
        {"code": b.code, "name_en": b.name_en, "name_ta": b.name_ta, "phone": b.phone, "active_loans": int(n),
         "outstanding": from_paise(int(out)), "overdue_amount": from_paise(int(od)), "overdue_days": int(days)}
        for b, out, od, days, n, _ in db.execute(stmt).all()
    ]


def dashboard(db: Session, business: BusinessSettings, today: date) -> dict[str, Any]:
    month_start = today.replace(day=1)
    principal_out = db.scalar(
        select(func.coalesce(func.sum(Loan.principal), 0)).where(Loan.status == "active", Loan.deleted_at.is_(None))
    )
    from app.models import ScheduleItem

    principal_remaining = db.scalar(
        select(func.coalesce(func.sum(ScheduleItem.principal_part - ScheduleItem.paid_principal
                                      - ScheduleItem.waived_principal), 0))
        .join(Loan, Loan.id == ScheduleItem.loan_id)
        .where(Loan.status == "active", Loan.deleted_at.is_(None))
    )
    to_receive = db.scalar(
        select(func.coalesce(func.sum(Loan.outstanding), 0)).where(Loan.status == "active", Loan.deleted_at.is_(None))
    )
    month = collections(db, month_start, today, "month")
    collected = month[0] if month else {"principal": 0, "interest": 0, "penalty": 0, "total": 0}
    c = dues.counts(db, business, today)
    active_loans = db.scalar(select(func.count()).select_from(Loan).where(Loan.status == "active",
                                                                          Loan.deleted_at.is_(None)))
    active_borrowers = db.scalar(
        select(func.count(func.distinct(Loan.borrower_id))).where(Loan.status == "active", Loan.deleted_at.is_(None))
    )
    return {
        "principal_outstanding": from_paise(int(principal_remaining or 0)),
        "principal_lent_active": from_paise(int(principal_out or 0)),
        "total_to_receive": from_paise(int(to_receive or 0)),
        "collected_this_month": collected,
        "interest_this_month": interest_earned(db, month_start, today)["interest"],
        "interest_to_date": interest_earned(db, None, today)["interest"],
        "due_today": c["due_today"],
        "overdue": c["overdue"],
        "long_unpaid": c["long_unpaid"],
        "upcoming": c["upcoming"],
        "ageing": c["ageing"],
        "active_loans": int(active_loans or 0),
        "active_borrowers": int(active_borrowers or 0),
    }


def to_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel opens Tamil correctly


def export(kind: str, lang: str, business: BusinessSettings, data: list[dict[str, Any]], *, fmt: str,
           subtitle: str | None) -> tuple[bytes, str]:
    def t(key: str) -> str:
        return i18n.t(lang, key)

    money = i18n.money
    if kind == "collections":
        headers = [t("report.period"), t("report.count"), t("receipt.principal"), t("receipt.interest"),
                   t("receipt.penalty"), t("receipt.total")]
        rows = [[i18n.fmt_date(r["period"]), r["count"], money(r["principal"], False), money(r["interest"], False),
                 money(r["penalty"], False), money(r["total"], False)] for r in data]
        numeric, title = {1, 2, 3, 4, 5}, t("report.collections")
    elif kind == "outstanding":
        headers = [t("receipt.code"), t("report.borrower"), t("report.loans"), t("statement.outstanding"),
                   t("report.overdue"), t("report.overdue_days")]
        rows = [[r["code"], i18n.name(lang, r["name_en"], r["name_ta"]), r["active_loans"],
                 money(r["outstanding"], False), money(r["overdue_amount"], False), r["overdue_days"]] for r in data]
        numeric, title = {2, 3, 4, 5}, t("report.outstanding")
    elif kind == "ageing":
        headers = [t("report.bucket"), t("report.count"), t("report.amount")]
        rows = [[t(f"bucket.{r['bucket']}"), r["count"], money(r["amount"], False)] for r in data]
        numeric, title = {1, 2}, t("report.ageing")
    else:  # interest
        headers = [t("report.period"), t("receipt.interest"), t("receipt.penalty")]
        rows = [[i18n.fmt_date(r["period"]), money(r["interest"], False), money(r["penalty"], False)] for r in data]
        numeric, title = {1, 2}, t("report.interest")
    if fmt == "csv":
        return to_csv(headers, rows), "text/csv; charset=utf-8"
    return pdf.table(lang, business, title=title, subtitle=subtitle, headers=headers, rows=rows,
                     numeric=numeric), "application/pdf"

