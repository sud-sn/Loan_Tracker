"""Loan creation, preview and detail (PRD section 4)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core import clock
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import LoanTerms, ScheduleResult, build_schedule, from_paise, q2, to_paise, true_cost
from app.engine.status import item_status
from app.engine.types import BrokenPeriod, CustomRow, FixedStyle, Frequency, Method, RateBasis, TermUnit
from app.models import Borrower, BusinessSettings, Collateral, Loan, LoanCharge, Payment, ScheduleItem
from app.repositories import counters
from app.schemas.loans import ChargeIn, LoanCreateIn, LoanUpdateIn, PaymentIn, SecurityIn, TermsIn
from app.services import audit, ledger

ZERO = Decimal("0.00")


def to_terms(data: TermsIn, principal: Decimal | None = None) -> LoanTerms:
    return LoanTerms(
        principal=principal if principal is not None else data.principal,
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
        emi_rounding=data.emi_rounding,
        advance_installments=data.advance_installments,
        broken_period=BrokenPeriod(data.broken_period),
    )


def security_value(sec: SecurityIn) -> Decimal | None:
    """The valuation used for loan-to-value: as entered, else the on-road price (vehicle), else the
    market value, else the guideline value (land)."""
    return sec.value or sec.on_road_price or sec.market_value or sec.guideline_value


@dataclass(frozen=True)
class Figures:
    """Everything worked out for a loan before it is saved (the preview shows the same)."""

    result: ScheduleResult
    rate_above: bool
    loan_amount: Decimal  # as entered, before charges added to it
    financed: Decimal  # the schedule's principal: loan amount + charges added
    charges_added: Decimal
    charges_deducted: Decimal  # includes extra days' interest collected up front
    handed_over: Decimal
    true_cost_monthly: Decimal | None
    true_cost_yearly: Decimal | None
    security_value: Decimal | None
    ltv_percent: Decimal | None
    ltv_maximum: Decimal | None
    ltv_above: bool


def figures(terms: TermsIn, charges: Sequence[ChargeIn], security: Sequence[SecurityIn],
            business: BusinessSettings) -> Figures:
    added = sum((c.amount for c in charges if c.treatment == "added"), ZERO)
    deducted = sum((c.amount for c in charges if c.treatment == "deducted"), ZERO)
    financed = terms.principal + added
    result = build_schedule(to_terms(terms, principal=financed))
    above = business.max_rate_monthly is not None and result.monthly_rate_equivalent > Decimal(business.max_rate_monthly)
    collected = deducted + result.broken_period_upfront
    handed_over = terms.principal - collected - result.advance_amount
    if handed_over <= 0:
        raise AppError("HANDED_OVER_NOT_POSITIVE", 422, handed_over=str(handed_over))
    # The borrower receives the loan amount less what is taken out; advance installments are
    # payments on day 0 and are part of the schedule.
    cost = true_cost(terms.disbursal_date, terms.principal - collected,
                     [(row.due_date, row.installment) for row in result.rows], Frequency(terms.frequency))
    values = [(sec.kind, security_value(sec)) for sec in security]
    total_value = sum((v for _, v in values if v), ZERO)
    ltv = ltv_max = None
    ltv_above = False
    if total_value > 0:
        allowed = sum(
            (v * Decimal(business.ltv_max_vehicle if kind == "vehicle" else business.ltv_max_land) / 100
             for kind, v in values if v),
            ZERO,
        )
        ltv = q2(financed / total_value * 100)
        ltv_max = q2(allowed / total_value * 100)
        ltv_above = financed > allowed
    return Figures(
        result=result, rate_above=above, loan_amount=q2(terms.principal), financed=q2(financed),
        charges_added=q2(added), charges_deducted=q2(collected), handed_over=q2(handed_over),
        true_cost_monthly=cost.monthly_percent if cost else None, true_cost_yearly=cost.yearly_percent if cost else None,
        security_value=q2(total_value) if total_value > 0 else None, ltv_percent=ltv, ltv_maximum=ltv_max,
        ltv_above=ltv_above,
    )


def preview_out(f: Figures, business: BusinessSettings) -> dict[str, Any]:
    result = f.result
    return {
        "installment": result.installment, "last_installment": result.last_installment,
        "total_principal": result.total_principal, "total_interest": result.total_interest,
        "total_payable": result.total_payable, "installments": result.installments,
        "first_due_date": result.first_due_date, "maturity_date": result.maturity_date,
        "monthly_rate_equivalent": result.monthly_rate_equivalent, "rate_above_maximum": f.rate_above,
        "max_rate_monthly": business.max_rate_monthly,
        "first_installment": result.first_installment, "unrounded_installment": result.unrounded_installment,
        "broken_period_days": result.broken_period_days, "broken_period_interest": result.broken_period_interest,
        "advance_installments": result.advance_installments, "advance_amount": result.advance_amount,
        "loan_amount": f.loan_amount, "charges_added": f.charges_added, "charges_deducted": f.charges_deducted,
        "odd_period_upfront": result.broken_period_upfront, "amount_handed_over": f.handed_over,
        "true_cost_monthly": f.true_cost_monthly, "true_cost_yearly": f.true_cost_yearly,
        "security_value": f.security_value, "ltv_percent": f.ltv_percent, "ltv_maximum": f.ltv_maximum,
        "ltv_above_maximum": f.ltv_above,
        "rows": [row.__dict__ for row in result.rows],
    }


def registration_key(text: str | None) -> str | None:
    """'TN 59 ab-1234' -> 'TN59AB1234', so a search finds it however it was typed."""
    key = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    return key or None


def _security_kind(security: Sequence[SecurityIn]) -> str:
    kinds = {sec.kind for sec in security}
    return "none" if not kinds else kinds.pop() if len(kinds) == 1 else "both"


def _collateral(loan_id: uuid.UUID, sec: SecurityIn) -> Collateral:
    data = sec.model_dump()
    money = ("value", "on_road_price", "down_payment", "guideline_value", "market_value")
    for name in money:
        data[name] = to_paise(data[name]) if data[name] is not None else None
    if data["value"] is None:
        value = security_value(sec)
        data["value"] = to_paise(value) if value else None
    return Collateral(loan_id=loan_id, registration_key=registration_key(sec.registration_no), **data)


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

    f = figures(data.terms, data.charges, data.security, ctx.business)
    result, above = f.result, f.rate_above
    if above and not data.acknowledge_rate_warning:
        raise AppError("RATE_ABOVE_MAXIMUM", 409, rate=str(result.monthly_rate_equivalent),
                       maximum=str(ctx.business.max_rate_monthly))
    if f.ltv_above and not data.acknowledge_ltv_warning:
        raise AppError("LTV_ABOVE_MAXIMUM", 409, ltv=str(f.ltv_percent), maximum=str(f.ltv_maximum))

    t = data.terms
    loan = Loan(
        loan_no=counters.next_loan_no(db, t.disbursal_date.year),
        borrower_id=borrower.id,
        principal=to_paise(f.financed),
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
        emi_rounding=q2(t.emi_rounding),
        advance_installments=t.advance_installments,
        broken_period=t.broken_period,
        broken_period_days=result.broken_period_days,
        broken_period_interest=to_paise(result.broken_period_interest),
        amount_handed_over=to_paise(f.handed_over),
        true_cost_monthly=f.true_cost_monthly,
        security_kind=_security_kind(data.security),
        ltv_percent=f.ltv_percent,
        ltv_warning_acknowledged=f.ltv_above,
        idempotency_key=data.idempotency_key,
        created_by=ctx.user.id,
        import_batch_id=import_batch_id,
    )
    db.add(loan)
    db.flush()
    loan.outstanding = to_paise(result.total_payable)
    loan.principal_outstanding = to_paise(f.financed)
    loan.next_unpaid_due = result.rows[0].due_date
    db.add_all(
        ScheduleItem(
            loan_id=loan.id, seq=row.seq, due_date=row.due_date, installment=to_paise(row.installment),
            principal_part=to_paise(row.principal_part), interest_part=to_paise(row.interest_part),
            closing_balance=to_paise(row.closing_balance),
        )
        for row in result.rows
    )
    db.add_all(
        LoanCharge(loan_id=loan.id, kind=c.kind, label=(c.label or "").strip() or None, amount=to_paise(c.amount),
                   treatment=c.treatment)
        for c in data.charges
    )
    if result.broken_period_upfront > 0:
        db.add(LoanCharge(loan_id=loan.id, kind="odd_period_interest", amount=to_paise(result.broken_period_upfront),
                          treatment="deducted"))
    db.add_all(_collateral(loan.id, sec) for sec in data.security)
    db.flush()
    audit.from_ctx(ctx, "loan.created", "loan", loan.id, {
        "loan_no": loan.loan_no, "borrower": borrower.code, "principal": str(f.financed), "method": t.method,
        "rate": str(t.rate), "installments": result.installments, "rate_above_maximum": above,
        "handed_over": str(f.handed_over), "charges": [f"{c.kind}:{c.treatment}:{c.amount}" for c in data.charges],
        "security": [sec.kind for sec in data.security], "ltv": str(f.ltv_percent) if f.ltv_percent else None,
        "ltv_above_maximum": f.ltv_above, "advance_installments": t.advance_installments,
    })
    if result.advance_amount > 0:
        # Advance installments are paid on the day the loan is given: record them as a payment so
        # they get a receipt and show as money in on the daily log.
        from app.services import payments  # local import: payments imports this module

        payments.record(ctx, loan.id, PaymentIn(
            amount=result.advance_amount, paid_on=t.disbursal_date, mode=data.disbursal_mode,
            idempotency_key=f"{data.idempotency_key}:advance",
        ), commit=False)
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
    all_items = ledger.load_items(db, loan.id, include_replaced=True) if detail else items
    states, pen = ledger.item_states(db, loan, items, today)
    s = ledger.summary(db, loan, items, today, business.due_soon_days)
    fees = loan.fees
    fees_due = from_paise(ledger.fees_due(fees))
    paid_total = (db.scalar(select(func.coalesce(func.sum(
        ScheduleItem.paid_principal + ScheduleItem.paid_interest + ScheduleItem.paid_penalty), 0))
        .where(ScheduleItem.loan_id == loan.id)) or 0) + sum(f.paid for f in fees)
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
        "emi_rounding": loan.emi_rounding, "advance_installments": loan.advance_installments,
        "broken_period": loan.broken_period, "broken_period_days": loan.broken_period_days,
        "broken_period_interest": from_paise(loan.broken_period_interest),
        "amount_handed_over": from_paise(loan.amount_handed_over), "true_cost_monthly": loan.true_cost_monthly,
        "security_kind": loan.security_kind, "ltv_percent": loan.ltv_percent,
        "charges": [
            {"kind": c.kind, "label": c.label, "amount": from_paise(c.amount), "treatment": c.treatment}
            for c in loan.charges
        ],
        "security": [_security_out(c) for c in loan.securities],
        "version": loan.version, "created_at": loan.created_at,
        "summary": {**s.__dict__, "status": s.status.value, "paid_total": from_paise(int(paid_total)),
                    "fees_outstanding": fees_due, "total_outstanding": s.total_outstanding + fees_due},
    }
    if detail:
        state_of = {it.id: st for it, st in zip(items, states, strict=True)}
        out["schedule"] = [
            {
                "id": it.id, "seq": it.seq, "due_date": it.due_date, "installment": from_paise(it.installment),
                "principal_part": from_paise(it.principal_part), "interest_part": from_paise(it.interest_part),
                "closing_balance": from_paise(it.closing_balance), "paid_principal": from_paise(it.paid_principal),
                "paid_interest": from_paise(it.paid_interest), "paid_penalty": from_paise(it.paid_penalty),
                "waived": from_paise(it.waived_principal + it.waived_interest + it.waived_penalty),
                "penalty_due": ZERO if it.replaced else pen[it.id],
                "unpaid": ZERO if it.replaced else from_paise(max(it.principal_due + it.interest_due, 0)),
                "status": "rescheduled" if it.replaced else item_status(state_of[it.id], today).value
                if loan.status == "active" or it.settled else "paid",
            }
            for it in all_items
        ]
        out["fees"] = [
            {"id": f.id, "kind": f.kind, "label": f.label, "amount": from_paise(f.amount), "charged_on": f.charged_on,
             "paid": from_paise(f.paid), "waived": from_paise(f.waived), "due": from_paise(f.due),
             "waive_reason": f.waive_reason, "note": f.note}
            for f in fees
        ]
        out["reschedules"] = [
            {"paid_on": r.paid_on, "extra": from_paise(r.extra), "mode": r.mode,
             "old_installment": from_paise(r.old_installment), "new_installment": from_paise(r.new_installment),
             "old_count": r.old_count, "new_count": r.new_count, "old_maturity": r.old_maturity,
             "new_maturity": r.new_maturity, "interest_saved": from_paise(r.interest_saved)}
            for r in loan.reschedules
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


def _security_out(c: Collateral) -> dict[str, Any]:
    out = {name: getattr(c, name) for name in SecurityIn.model_fields}
    for name in ("value", "on_road_price", "down_payment", "guideline_value", "market_value"):
        out[name] = from_paise(out[name]) if out[name] is not None else None
    return {**out, "id": c.id, "version": c.version}
