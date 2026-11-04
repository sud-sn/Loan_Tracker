"""Loan creation, preview and detail (PRD section 4)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core import clock
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import LoanTerms, ScheduleResult, build_schedule, from_paise, to_paise
from app.engine.status import item_status
from app.engine.types import CustomRow, FixedStyle, Frequency, Method, RateBasis, TermUnit
from app.models import Borrower, BusinessSettings, Loan, Payment, ScheduleItem
from app.repositories import counters
from app.schemas.loans import LoanCreateIn, LoanUpdateIn, TermsIn
from app.services import audit, ledger


def to_terms(data: TermsIn) -> LoanTerms:
    return LoanTerms(
        principal=data.principal,
        rate=data.rate,
        rate_basis=RateBasis(data.rate_basis),
        term_value=data.term_value,
        term_unit=TermUnit(data.term_unit),
        frequency=Frequency(data.frequency),
        method=Method(data.method),
        disbursal_date=data.disbursal_date,
        first_due_date=data.first_due_date,
        fixed_installment=data.fixed_installment,
        fixed_style=FixedStyle(data.fixed_style),
        custom_principal=data.custom_principal,
        custom_interest=data.custom_interest,
        custom_rows=tuple(CustomRow(r.principal_part, r.interest_part) for r in data.custom_rows)
        if data.custom_rows else None,
    )


def preview(data: TermsIn, business: BusinessSettings) -> tuple[ScheduleResult, bool]:
    result = build_schedule(to_terms(data))
    above = business.max_rate_monthly is not None and result.monthly_rate_equivalent > Decimal(
        business.max_rate_monthly
    )
    return result, above


def preview_out(result: ScheduleResult, above: bool, business: BusinessSettings) -> dict[str, Any]:
    return {
        "installment": result.installment, "last_installment": result.last_installment,
        "total_principal": result.total_principal, "total_interest": result.total_interest,
        "total_payable": result.total_payable, "installments": result.installments,
        "first_due_date": result.first_due_date, "maturity_date": result.maturity_date,
        "monthly_rate_equivalent": result.monthly_rate_equivalent, "rate_above_maximum": above,
        "max_rate_monthly": business.max_rate_monthly,
        "rows": [row.__dict__ for row in result.rows],
    }


def create(ctx: Ctx, data: LoanCreateIn, *, import_batch_id: uuid.UUID | None = None,
           commit: bool = True) -> Loan:
    db = ctx.db
    existing = db.scalars(select(Loan).where(Loan.idempotency_key == data.idempotency_key)).first()
    if existing is not None:
        return existing
    borrower = db.scalars(
        select(Borrower).where(Borrower.id == data.borrower_id, Borrower.deleted_at.is_(None)).with_for_update()
    ).first()
    if borrower is None:
        raise AppError("BORROWER_NOT_FOUND", 404)
    if borrower.status != "active":
        raise AppError("BORROWER_NOT_ACTIVE", 409, status=borrower.status)
    if borrower.aadhaar_hash is None and import_batch_id is None:
        raise AppError("BORROWER_INCOMPLETE", 409)
    if data.terms.disbursal_date > clock.today():
        raise AppError("DATE_IN_FUTURE", 422)

    result, above = preview(data.terms, ctx.business)
    if above and not data.acknowledge_rate_warning:
        raise AppError("RATE_ABOVE_MAXIMUM", 409, rate=str(result.monthly_rate_equivalent),
                       maximum=str(ctx.business.max_rate_monthly))

    t = data.terms
    loan = Loan(
        loan_no=counters.next_loan_no(db, t.disbursal_date.year),
        borrower_id=borrower.id,
        principal=to_paise(t.principal),
        rate=t.rate,
        rate_basis=t.rate_basis,
        term_value=t.term_value if t.method not in ("fixed_amount",) else result.installments,
        term_unit=t.term_unit if t.method not in ("fixed_amount",) else "installments",
        frequency=t.frequency,
        method=t.method,
        fixed_style=t.fixed_style if t.method == "fixed_amount" else None,
        fixed_installment=to_paise(t.fixed_installment) if t.fixed_installment else None,
        custom_principal=to_paise(t.custom_principal) if t.custom_principal else None,
        custom_interest=to_paise(t.custom_interest) if t.custom_interest is not None else None,
        terms_json=t.model_dump(mode="json"),
        installments=result.installments,
        installment_amount=to_paise(result.installment),
        total_interest=to_paise(result.total_interest),
        disbursal_date=t.disbursal_date,
        first_due_date=result.first_due_date,
        maturity_date=result.maturity_date,
        disbursal_mode=data.disbursal_mode,
        penalty_mode=data.penalty.mode,
        penalty_value=data.penalty.value,
        penalty_grace_days=data.penalty.grace_days,
        purpose=data.purpose,
        notes=data.notes,
        rate_warning_acknowledged=above,
        idempotency_key=data.idempotency_key,
        created_by=ctx.user.id,
        import_batch_id=import_batch_id,
    )
    db.add(loan)
    db.flush()
    loan.outstanding = to_paise(result.total_payable)
    db.add_all(
        ScheduleItem(
            loan_id=loan.id, seq=row.seq, due_date=row.due_date, installment=to_paise(row.installment),
            principal_part=to_paise(row.principal_part), interest_part=to_paise(row.interest_part),
            closing_balance=to_paise(row.closing_balance),
        )
        for row in result.rows
    )
    db.flush()
    audit.from_ctx(ctx, "loan.created", "loan", loan.id, {
        "loan_no": loan.loan_no, "borrower": borrower.code, "principal": str(t.principal), "method": t.method,
        "rate": str(t.rate), "installments": result.installments, "rate_above_maximum": above,
    })
    if commit:
        db.commit()
    return loan


def get(db: Session, loan_id: uuid.UUID) -> Loan:
    loan = db.scalars(
        select(Loan).options(joinedload(Loan.borrower)).where(Loan.id == loan_id, Loan.deleted_at.is_(None))
    ).first()
    if loan is None:
        raise AppError("LOAN_NOT_FOUND", 404)
    return loan


def borrower_ref(b: Borrower) -> dict[str, Any]:
    return {"id": b.id, "code": b.code, "name_en": b.name_en, "name_ta": b.name_ta, "phone": b.phone,
            "preferred_language": b.preferred_language}


def serialize(db: Session, loan: Loan, business: BusinessSettings, *, detail: bool = False) -> dict[str, Any]:
    from app.services import payments  # local import: payments imports this module

    today = clock.today()
    items = ledger.load_items(db, loan.id)
    states, pen = ledger.item_states(db, loan, items, today)
    s = ledger.summary(db, loan, items, today, business.due_soon_days)
    paid_total = sum(it.paid_principal + it.paid_interest + it.paid_penalty for it in items)
    out: dict[str, Any] = {
        "id": loan.id, "loan_no": loan.loan_no, "borrower": borrower_ref(loan.borrower),
        "principal": from_paise(loan.principal), "rate": loan.rate, "rate_basis": loan.rate_basis,
        "term_value": loan.term_value, "term_unit": loan.term_unit, "frequency": loan.frequency,
        "method": loan.method, "fixed_style": loan.fixed_style,
        "fixed_installment": from_paise(loan.fixed_installment) if loan.fixed_installment else None,
        "installments": loan.installments, "installment_amount": from_paise(loan.installment_amount),
        "total_interest": from_paise(loan.total_interest), "disbursal_date": loan.disbursal_date,
        "first_due_date": loan.first_due_date, "maturity_date": loan.maturity_date,
        "disbursal_mode": loan.disbursal_mode, "penalty_mode": loan.penalty_mode,
        "penalty_value": loan.penalty_value, "penalty_grace_days": loan.penalty_grace_days,
        "stored_status": loan.status, "closed_on": loan.closed_on, "closed_reason": loan.closed_reason,
        "last_payment_on": loan.last_payment_on, "purpose": loan.purpose, "notes": loan.notes,
        "version": loan.version, "created_at": loan.created_at,
        "summary": {**s.__dict__, "status": s.status.value, "paid_total": from_paise(paid_total)},
    }
    if detail:
        out["schedule"] = [
            {
                "id": it.id, "seq": it.seq, "due_date": it.due_date, "installment": from_paise(it.installment),
                "principal_part": from_paise(it.principal_part), "interest_part": from_paise(it.interest_part),
                "closing_balance": from_paise(it.closing_balance), "paid_principal": from_paise(it.paid_principal),
                "paid_interest": from_paise(it.paid_interest), "paid_penalty": from_paise(it.paid_penalty),
                "waived": from_paise(it.waived_principal + it.waived_interest + it.waived_penalty),
                "penalty_due": pen[it.id],
                "unpaid": from_paise(max(it.principal_due + it.interest_due, 0)),
                "status": item_status(st, today).value
                if loan.status == "active" or it.settled else "paid",
            }
            for it, st in zip(items, states, strict=True)
        ]
        pays = db.scalars(
            select(Payment).where(Payment.loan_id == loan.id).order_by(Payment.paid_on.desc(), Payment.created_at.desc())
        ).all()
        out["payments"] = [payments.serialize(db, p) for p in pays]
    return out


def update(ctx: Ctx, loan_id: uuid.UUID, data: LoanUpdateIn) -> Loan:
    loan = get(ctx.db, loan_id)
    if loan.version != data.version:
        raise AppError("EDIT_CONFLICT", 409)
    changes = {}
    for field in ("purpose", "notes"):
        new = getattr(data, field)
        if new != getattr(loan, field):
            changes[field] = [getattr(loan, field), new]
            setattr(loan, field, new)
    audit.from_ctx(ctx, "loan.updated", "loan", loan.id, changes)
    ctx.db.commit()
    return loan


def soft_delete(ctx: Ctx, loan_id: uuid.UUID) -> None:
    loan = get(ctx.db, loan_id)
    if ctx.db.scalars(select(Payment.id).where(Payment.loan_id == loan.id).limit(1)).first():
        raise AppError("LOAN_HAS_PAYMENTS", 409)
    loan.deleted_at = clock_now()
    audit.from_ctx(ctx, "loan.deleted", "loan", loan.id, {"loan_no": loan.loan_no})
    ctx.db.commit()


def clock_now() -> Any:
    from app.security.tokens import now

    return now()
