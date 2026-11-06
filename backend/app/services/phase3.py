"""Phase 3: restructure, seizure and sale, release of security, cheque register, insurance.

* Restructure (relief for a borrower): every installment not yet paid is replaced. Unpaid principal
  is spread over the new installments; overdue interest and the interest of any skipped
  installments (an EMI holiday) are spread evenly over them too. Installments can be added to
  lower the EMI, and the rate can change from here on. The late fee must be collected or waived
  first. The history keeps the old rows ("Rescheduled") and a restructure line. See ADR-0016.
* Seizure and sale: the vehicle is marked seized (towing / yard charges can be added). When it is
  sold, sale expenses become a charge; if the sale covers what closing the loan costs (interest
  to the day, no foreclosure charge) the loan is closed and any surplus is given back to the
  borrower; otherwise the sale price is paid into the loan and the rest is still owed.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core import clock
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import from_paise, to_paise
from app.engine.dates import due_dates, one_period_after
from app.engine.money import ZERO, q2
from app.engine.reschedule import Style
from app.engine.schedule import _equal_split, _flat_parts_ext, _interest_only_parts, _reducing_parts_ext, periodic_rate
from app.engine.settlement import Rebate
from app.engine.types import Frequency, RateBasis
from app.models import Borrower, Cheque, Collateral, Loan, LoanFee, Refund, Reschedule, ScheduleItem
from app.schemas.loans import (
    ChequeIn,
    ChequeStatusIn,
    PaymentIn,
    ReleaseIn,
    RestructureIn,
    SecurityUpdateIn,
    SeizeIn,
    SellIn,
    SettleIn,
)
from app.services import audit, ledger
from app.services import payments as pay
from app.services.loans import registration_key
from app.services.phase2 import _loan, _style, current_rate

# ------------------------------------------------------------------- restructure

def _restructure_plan(db: Any, loan: Loan, items: list[ScheduleItem], data: RestructureIn, on: date) -> dict[str, Any]:
    style = _style(loan)
    if any(v > 0 for v in ledger.penalty_due(db, loan, items, on).values()):
        raise AppError("LATE_FEE_DUE_FIRST", 409)
    unpaid = [it for it in items if not it.settled]
    if not unpaid:
        raise AppError("NOTHING_TO_RESCHEDULE", 422)
    freq = Frequency(loan.frequency)
    rate = data.new_rate if data.new_rate is not None else current_rate(loan)
    r = periodic_rate(rate, RateBasis(loan.rate_basis), freq)
    balance = from_paise(sum(max(it.principal_due, 0) for it in unpaid))
    overdue_interest = from_paise(sum(max(it.interest_due, 0) for it in unpaid if it.due_date <= on))
    holiday_interest = q2(balance * r * data.holiday) if style is not Style.FLAT else q2(
        from_paise(loan.principal) * r * data.holiday)
    carried = overdue_interest + holiday_interest
    future = [it for it in unpaid if it.due_date > on]
    base_first = future[0].due_date if future else one_period_after(on, freq)
    first_due = due_dates(base_first, data.holiday + 1, freq)[-1]
    n = len(unpaid) + data.extra_installments
    step = Decimal(loan.emi_rounding)
    if style is Style.INTEREST_ONLY:
        parts = _interest_only_parts(balance, r, n)
    elif style is Style.REDUCING:
        parts = _reducing_parts_ext(balance, r, n, 0, step)[0]
    else:
        parts = _flat_parts_ext(balance, r, n, step)[0]
    spread = _equal_split(carried, len(parts)) if carried > 0 else [ZERO] * len(parts)
    parts = [(p, i + extra) for (p, i), extra in zip(parts, spread, strict=True)]
    dates = due_dates(first_due, len(parts), freq)
    rows: list[dict[str, Any]] = []
    left = balance
    for seq, ((p, i), due) in enumerate(zip(parts, dates, strict=True), start=1):
        left -= p
        rows.append({"seq": seq, "due_date": due, "installment": p + i, "principal_part": p, "interest_part": i,
                     "closing_balance": left})
    installments = [row["installment"] for row in rows]
    new_installment = installments[1] if len(installments) > 2 else installments[0]
    old_interest = from_paise(sum(max(it.interest_due, 0) for it in unpaid))
    new_interest: Decimal = sum((Decimal(row["interest_part"]) for row in rows), ZERO)
    return {
        "on": on, "principal": balance, "carried_interest": carried,
        "old_installment": from_paise(loan.installment_amount), "new_installment": new_installment,
        "old_count": len(items), "new_count": len(items) - len(unpaid) + len(rows),
        "old_maturity": loan.maturity_date, "new_maturity": dates[-1], "rate": rate,
        "interest_change": new_interest - old_interest, "rows": rows, "_unpaid": unpaid,
    }


def restructure_preview(ctx: Ctx, loan_id: uuid.UUID, data: RestructureIn) -> dict[str, Any]:
    loan = ctx.db.get(Loan, loan_id)
    if loan is None or loan.status != "active":
        raise AppError("LOAN_NOT_ACTIVE", 409)
    plan = _restructure_plan(ctx.db, loan, ledger.load_items(ctx.db, loan.id), data, data.on or clock.today())
    plan.pop("_unpaid")
    return plan


def restructure(ctx: Ctx, loan_id: uuid.UUID, data: RestructureIn) -> Loan:
    db = ctx.db
    loan = _loan(ctx, loan_id)
    if data.version is not None and data.version != loan.version:
        raise AppError("EDIT_CONFLICT", 409)
    on = data.on or clock.today()
    pay._check_date(loan, on)
    items = ledger.load_items(db, loan.id, lock=True)
    plan = _restructure_plan(db, loan, items, data, on)
    for it in plan["_unpaid"]:
        it.replaced = True
        it.settled = True
    next_seq = (db.scalar(select(func.max(ScheduleItem.seq)).where(ScheduleItem.loan_id == loan.id)) or 0) + 1
    new_items = [
        ScheduleItem(loan_id=loan.id, seq=next_seq + k, due_date=row["due_date"], installment=to_paise(row["installment"]),
                     principal_part=to_paise(row["principal_part"]), interest_part=to_paise(row["interest_part"]),
                     closing_balance=to_paise(row["closing_balance"]))
        for k, row in enumerate(plan["rows"])
    ]
    db.add_all(new_items)
    db.flush()
    current = [it for it in items if not it.replaced] + new_items
    replaced = [it for it in ledger.load_items(db, loan.id, include_replaced=True) if it.replaced]
    loan.installment_amount = to_paise(plan["new_installment"])
    loan.installments = len(current)
    loan.maturity_date = plan["new_maturity"]
    loan.total_interest = (sum(it.interest_part for it in current)
                           + sum(it.paid_interest + it.waived_interest for it in replaced))
    db.add(Reschedule(
        loan_id=loan.id, payment_id=None, paid_on=on, extra=0, mode="restructure", kind="restructure",
        old_installment=to_paise(plan["old_installment"]), new_installment=to_paise(plan["new_installment"]),
        old_count=plan["old_count"], new_count=plan["new_count"], old_maturity=plan["old_maturity"],
        new_maturity=plan["new_maturity"], interest_saved=-to_paise(plan["interest_change"]),
        new_rate=data.new_rate, holiday_months=data.holiday, reason=data.reason, created_by=ctx.user.id,
    ))
    ledger.refresh_loan_cache(loan, current)
    audit.from_ctx(ctx, "loan.restructured", "loan", loan.id, {
        "loan_no": loan.loan_no, "holiday": data.holiday, "extra_installments": data.extra_installments,
        "new_rate": str(data.new_rate) if data.new_rate is not None else None, "reason": data.reason,
        "new_installment": str(plan["new_installment"]), "interest_change": str(plan["interest_change"]),
    })
    db.commit()
    return loan


# ------------------------------------------------------------------- seizure and sale

def seize(ctx: Ctx, loan_id: uuid.UUID, data: SeizeIn) -> Loan:
    loan = _loan(ctx, loan_id)
    if not any(c.kind == "vehicle" for c in loan.securities):
        raise AppError("NO_VEHICLE_SECURITY", 409)
    on = data.on or clock.today()
    pay._check_date(loan, on)
    loan.recovery_status, loan.seized_on, loan.seizure_note = "seized", on, data.note
    if data.charge and data.charge > 0:
        ctx.db.add(LoanFee(loan_id=loan.id, kind="seizure", amount=to_paise(data.charge), charged_on=on,
                           note=data.note, created_by=ctx.user.id))
    audit.from_ctx(ctx, "loan.seized", "loan", loan.id, {"loan_no": loan.loan_no, "on": on.isoformat(), "note": data.note})
    ctx.db.commit()
    return loan


def sell(ctx: Ctx, loan_id: uuid.UUID, data: SellIn) -> dict[str, Any]:
    db = ctx.db
    loan = _loan(ctx, loan_id)
    if loan.recovery_status != "seized":
        raise AppError("NOT_SEIZED", 409)
    on = data.on or clock.today()
    pay._check_date(loan, on)
    if data.expenses > 0:
        db.add(LoanFee(loan_id=loan.id, kind="seizure", label=None, amount=to_paise(data.expenses), charged_on=on,
                       note="sale expenses", created_by=ctx.user.id))
        db.flush()
    closing = pay.settlement_figure(db, loan, on, ctx.business, Rebate.PRO_RATA, Decimal("0"))
    loan.recovery_status = "sold"
    note = f"vehicle sold{': ' + data.note if data.note else ''}"
    if data.sale_price >= closing.total:
        db.commit()
        pay.settle(ctx, loan.id, SettleIn(on=on, expected_total=closing.total, foreclosure_charge=Decimal("0"),
                                          mode=data.mode, reference="SALE", idempotency_key=data.idempotency_key))
        surplus = data.sale_price - closing.total
        if surplus > 0:
            db.add(Refund(loan_id=loan.id, amount=to_paise(surplus), refunded_on=on, mode=data.mode,
                          reason=note, created_by=ctx.user.id))
        audit.from_ctx(ctx, "loan.vehicle_sold", "loan", loan.id, {"loan_no": loan.loan_no, "sale_price": str(data.sale_price),
                                                                     "refund": str(surplus)})
        db.commit()
        return {"closed": True, "paid_to_loan": closing.total, "refund": surplus, "shortfall": ZERO}
    db.commit()
    pay.record(ctx, loan.id, PaymentIn(amount=data.sale_price, paid_on=on, mode=data.mode, reference="SALE", note=note,
                                       idempotency_key=data.idempotency_key))
    audit.from_ctx(ctx, "loan.vehicle_sold", "loan", loan.id, {"loan_no": loan.loan_no, "sale_price": str(data.sale_price),
                                                                 "shortfall": str(closing.total - data.sale_price)})
    db.commit()
    return {"closed": False, "paid_to_loan": data.sale_price, "refund": ZERO, "shortfall": closing.total - data.sale_price}


# ------------------------------------------------------------------- security

def _collateral(ctx: Ctx, collateral_id: uuid.UUID) -> Collateral:
    c = ctx.db.scalars(select(Collateral).where(Collateral.id == collateral_id).with_for_update()).first()
    if c is None:
        raise AppError("SECURITY_NOT_FOUND", 404)
    return c


def update_security(ctx: Ctx, collateral_id: uuid.UUID, data: SecurityUpdateIn) -> Collateral:
    c = _collateral(ctx, collateral_id)
    if data.version != c.version:
        raise AppError("EDIT_CONFLICT", 409)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    for name, value in changes.items():
        setattr(c, name, value)
    if "registration_no" in changes:
        c.registration_key = registration_key(c.registration_no)
    audit.from_ctx(ctx, "security.updated", "loan", c.loan_id, {k: str(v) for k, v in changes.items()})
    ctx.db.commit()
    return c


def release(ctx: Ctx, collateral_id: uuid.UUID, data: ReleaseIn) -> Collateral:
    c = _collateral(ctx, collateral_id)
    loan = ctx.db.get(Loan, c.loan_id)
    if loan is None or loan.status != "closed":
        raise AppError("LOAN_NOT_CLOSED", 409)
    c.released_on, c.released_to = data.released_on or clock.today(), data.released_to
    audit.from_ctx(ctx, "security.released", "loan", c.loan_id, {"to": data.released_to})
    ctx.db.commit()
    return c


def insurance_due(db: Any, today: date, days: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Collateral, Loan, Borrower).join(Loan, Loan.id == Collateral.loan_id)
        .join(Borrower, Borrower.id == Loan.borrower_id)
        .where(Collateral.kind == "vehicle", Collateral.insurance_expiry.is_not(None),
               Collateral.insurance_expiry <= today + timedelta(days=days), Loan.status == "active",
               Loan.deleted_at.is_(None))
        .order_by(Collateral.insurance_expiry)
    ).all()
    from app.services.loans import borrower_ref

    return [{"loan_id": loan.id, "loan_no": loan.loan_no, "borrower": borrower_ref(b), "registration_no": c.registration_no,
             "insurer": c.insurer, "insurance_expiry": c.insurance_expiry, "expired": c.insurance_expiry < today}
            for c, loan, b in rows]


# ------------------------------------------------------------------- cheques

def add_cheque(ctx: Ctx, loan_id: uuid.UUID, data: ChequeIn) -> Cheque:
    loan = _loan(ctx, loan_id)
    cheque = Cheque(loan_id=loan.id, cheque_no=data.cheque_no.strip(), bank=data.bank, amount=to_paise(data.amount),
                    cheque_date=data.cheque_date, note=data.note)
    ctx.db.add(cheque)
    audit.from_ctx(ctx, "cheque.added", "loan", loan.id, {"cheque_no": data.cheque_no, "amount": str(data.amount)})
    ctx.db.commit()
    return cheque


def cheque_status(ctx: Ctx, cheque_id: uuid.UUID, data: ChequeStatusIn) -> Cheque:
    cheque = ctx.db.scalars(select(Cheque).where(Cheque.id == cheque_id).with_for_update()).first()
    if cheque is None:
        raise AppError("CHEQUE_NOT_FOUND", 404)
    if data.version != cheque.version:
        raise AppError("EDIT_CONFLICT", 409)
    on = data.on or clock.today()
    cheque.status, cheque.status_on = data.status, on
    if data.status == "bounced" and cheque.fee_id is None and ctx.business.bounce_charge_default > 0:
        loan = _loan(ctx, cheque.loan_id)
        fee = LoanFee(loan_id=loan.id, kind="bounce", amount=ctx.business.bounce_charge_default, charged_on=on,
                      note=f"cheque {cheque.cheque_no}", created_by=ctx.user.id)
        ctx.db.add(fee)
        ctx.db.flush()
        cheque.fee_id = fee.id
    audit.from_ctx(ctx, "cheque.status", "loan", cheque.loan_id, {"cheque_no": cheque.cheque_no, "status": data.status})
    ctx.db.commit()
    return cheque
