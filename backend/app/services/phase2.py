"""Phase 2: charges after the loan is given, waivers, and part-prepayment with a new schedule.

* A charge (bounced cheque, seizure, legal notice ...) is owed from the day it is added; payments
  pay charges first. The owner can waive all or part of it, with a reason.
* A late-fee waiver reduces the late fee due on overdue installments, oldest first.
* A part-prepayment first pays whatever is due on that day (charges, late fee, installments due),
  then the extra goes to principal and the installments not yet due are replaced by new ones on
  the same dates: smaller (``reduce_emi``) or fewer (``reduce_term``). See ADR-0015.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core import clock
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import EngineError, from_paise, to_paise
from app.engine.allocation import OpenItem, allocate
from app.engine.money import ZERO
from app.engine.reschedule import RescheduleMode, RescheduleResult, Style, reschedule
from app.engine.schedule import periodic_rate
from app.engine.types import Frequency, RateBasis
from app.models import Loan, LoanAdjustment, LoanFee, Payment, Reschedule, ScheduleItem
from app.schemas.loans import FeeIn, PrepayIn, WaiveIn
from app.services import audit, ledger
from app.services import payments as pay


def _loan(ctx: Ctx, loan_id: uuid.UUID) -> Loan:
    loan = ledger.lock_loan(ctx.db, loan_id)
    if loan is None:
        raise AppError("LOAN_NOT_FOUND", 404)
    if loan.status != "active":
        raise AppError("LOAN_NOT_ACTIVE", 409, status=loan.status)
    return loan


# ------------------------------------------------------------------- charges

def add_fee(ctx: Ctx, loan_id: uuid.UUID, data: FeeIn) -> LoanFee:
    loan = _loan(ctx, loan_id)
    on = data.charged_on or clock.today()
    pay._check_date(loan, on)
    fee = LoanFee(loan_id=loan.id, kind=data.kind, label=(data.label or "").strip() or None, amount=to_paise(data.amount),
                  charged_on=on, note=data.note, created_by=ctx.user.id)
    ctx.db.add(fee)
    ctx.db.flush()
    audit.from_ctx(ctx, "fee.added", "loan", loan.id, {"loan_no": loan.loan_no, "kind": data.kind,
                                                       "amount": str(data.amount), "on": on.isoformat()})
    ctx.db.commit()
    return fee


def waive_fee(ctx: Ctx, fee_id: uuid.UUID, data: WaiveIn) -> LoanFee:
    fee = ctx.db.scalars(select(LoanFee).where(LoanFee.id == fee_id).with_for_update()).first()
    if fee is None:
        raise AppError("FEE_NOT_FOUND", 404)
    loan = _loan(ctx, fee.loan_id)
    amount = to_paise(data.amount) if data.amount is not None else fee.due
    if amount <= 0 or amount > fee.due:
        raise AppError("WAIVER_TOO_LARGE", 422, due=str(from_paise(fee.due)))
    fee.waived += amount
    fee.waive_reason = data.reason
    pay._maybe_close(ctx.db, loan, ledger.load_items(ctx.db, loan.id), clock.today(), "paid")
    audit.from_ctx(ctx, "fee.waived", "loan", loan.id, {"loan_no": loan.loan_no, "kind": fee.kind,
                                                        "amount": str(from_paise(amount)), "reason": data.reason})
    ctx.db.commit()
    return fee


def waive_late_fee(ctx: Ctx, loan_id: uuid.UUID, data: WaiveIn) -> Decimal:
    """Waive the late fee due today, all or part, oldest installment first."""
    loan = _loan(ctx, loan_id)
    today = clock.today()
    items = ledger.load_items(ctx.db, loan.id, lock=True)
    pen = ledger.penalty_due(ctx.db, loan, items, today)
    total = sum(pen.values(), ZERO)
    want = data.amount if data.amount is not None else total
    if total <= 0 or want > total:
        raise AppError("WAIVER_TOO_LARGE", 422, due=str(total))
    left = to_paise(want)
    for it in items:
        if left <= 0:
            break
        take = min(left, to_paise(pen[it.id]))
        if take <= 0:
            continue
        ctx.db.add(LoanAdjustment(loan_id=loan.id, schedule_item_id=it.id, kind="penalty_waiver", adjusted_on=today,
                                  penalty_part=take, interest_part=0, principal_part=0, reason=data.reason,
                                  created_by=ctx.user.id))
        ledger.waive_on_item(it, take, 0, 0)
        left -= take
    pay._maybe_close(ctx.db, loan, items, today, "paid")
    audit.from_ctx(ctx, "late_fee.waived", "loan", loan.id, {"loan_no": loan.loan_no, "amount": str(want),
                                                             "reason": data.reason})
    ctx.db.commit()
    return want


# ------------------------------------------------------------------- part-prepayment

STYLES = {"reducing": Style.REDUCING, "flat": Style.FLAT, "interest_only": Style.INTEREST_ONLY}


@dataclass
class Plan:
    on: date
    dues: Decimal
    extra: Decimal
    principal_before: Decimal
    future: list[ScheduleItem]
    result: RescheduleResult
    interest_saved: Decimal


def current_rate(loan: Loan) -> Decimal:
    """The rate in force: the latest restructure's new rate, else the loan's own (Phase 3)."""
    for r in reversed(loan.reschedules):
        if r.new_rate is not None:
            return Decimal(r.new_rate)
    return Decimal(loan.rate)


def _style(loan: Loan) -> Style:
    if loan.method == "fixed_amount":
        return Style.REDUCING if loan.fixed_style == "reducing" else Style.FLAT
    if loan.method not in STYLES:
        raise AppError("PREPAY_NOT_FOR_METHOD", 422, method=loan.method)
    return STYLES[loan.method]


def plan(db: Any, loan: Loan, items: list[ScheduleItem], fees: list[LoanFee], amount: Decimal, on: date,
         mode: RescheduleMode) -> Plan:
    pay._check_date(loan, on)
    style = _style(loan)
    pen = ledger.penalty_due(db, loan, items, on)
    due_items = [it for it in items if it.due_date <= on]
    dues = (from_paise(ledger.fees_due(fees, on))
            + sum((pen[it.id] + from_paise(max(it.principal_due + it.interest_due, 0)) for it in due_items), ZERO))
    extra = amount - dues
    if extra <= 0:
        raise AppError("PREPAY_LESS_THAN_DUES", 422, dues=str(dues))
    future = [it for it in items if it.due_date > on]
    if not future:
        raise AppError("NOTHING_TO_RESCHEDULE", 422)
    owed = from_paise(sum(max(it.principal_due, 0) for it in future))
    if extra >= owed:
        raise AppError("PREPAY_USE_SETTLEMENT", 422, owed=str(owed))
    earlier = [it for it in items if it.seq < future[0].seq]
    period_start = earlier[-1].due_date if earlier else loan.disbursal_date
    try:
        result = reschedule(
            balance=owed - extra, rate=periodic_rate(current_rate(loan), RateBasis(loan.rate_basis), Frequency(loan.frequency)),
            style=style, mode=mode, dates=[it.due_date for it in future],
            old_installment=from_paise(loan.installment_amount), old_first_interest=from_paise(future[0].interest_part),
            period_start=period_start, paid_on=on, step=Decimal(loan.emi_rounding),
        )
    except EngineError:
        raise
    # Interest already paid in advance on the replaced rows is credited to the first new ones.
    credit = sum(it.paid_interest for it in future)
    parts = []
    for p, i in result.parts:
        take = min(credit, to_paise(i))
        credit -= take
        parts.append((p, i - from_paise(take)))
    result = RescheduleResult(tuple(parts), result.dates, result.installment, sum((i for _, i in parts), ZERO))
    old_interest = from_paise(sum(max(it.interest_due, 0) for it in future))
    return Plan(on, dues, extra, owed, future, result, max(old_interest - result.total_interest, ZERO))


def preview(ctx: Ctx, loan_id: uuid.UUID, amount: Decimal, on: date | None, mode: str) -> dict[str, Any]:
    loan = ctx.db.get(Loan, loan_id)
    if loan is None or loan.status != "active":
        raise AppError("LOAN_NOT_ACTIVE", 409)
    items = ledger.load_items(ctx.db, loan.id)
    p = plan(ctx.db, loan, items, ledger.load_fees(ctx.db, loan.id), amount, on or clock.today(), RescheduleMode(mode))
    return _preview_out(loan, items, p)


def _preview_out(loan: Loan, items: list[ScheduleItem], p: Plan) -> dict[str, Any]:
    balance = p.principal_before - p.extra
    rows = []
    for seq, ((pr, i), due) in enumerate(zip(p.result.parts, p.result.dates, strict=True), start=1):
        balance -= pr
        rows.append({"seq": seq, "due_date": due, "installment": pr + i, "principal_part": pr, "interest_part": i,
                     "closing_balance": balance})
    kept = [it for it in items if it not in p.future]
    return {
        "paid_on": p.on, "dues": p.dues, "extra": p.extra, "principal_before": p.principal_before,
        "principal_after": p.principal_before - p.extra, "old_installment": from_paise(loan.installment_amount),
        "new_installment": p.result.installment, "old_count": len(items), "new_count": len(kept) + len(p.result.parts),
        "old_maturity": loan.maturity_date, "new_maturity": p.result.dates[-1], "interest_saved": p.interest_saved,
        "rows": rows,
    }


def prepay(ctx: Ctx, loan_id: uuid.UUID, data: PrepayIn) -> Payment:
    db = ctx.db
    on = data.paid_on or clock.today()
    request_hash = pay._request_hash({"prepay": str(loan_id), "amount": str(data.amount), "on": on.isoformat(),
                                      "mode": data.mode_of_reschedule})
    if (hit := pay._replay(db, data.idempotency_key, request_hash)) is not None:
        return hit
    loan = _loan(ctx, loan_id)
    items = ledger.load_items(db, loan.id, lock=True)
    fees = ledger.load_fees(db, loan.id, lock=True)
    p = plan(db, loan, items, fees, data.amount, on, RescheduleMode(data.mode_of_reschedule))
    summary = _preview_out(loan, items, p)

    # 1. What is due by then: charges, then installments due (late fee, interest, principal).
    fee_lines = pay._fee_lines(fees, to_paise(p.dues), on)
    rest = p.dues - from_paise(sum(a for _, a in fee_lines))
    pen = ledger.penalty_due(db, loan, items, on)
    due_items = [it for it in items if it.due_date <= on]
    by_id = {str(it.id): it for it in items}
    lines = [
        (by_id[ln.item_id], to_paise(ln.penalty_part), to_paise(ln.interest_part), to_paise(ln.principal_part))
        for ln in (allocate(rest, [OpenItem(str(it.id), it.seq, pen[it.id], from_paise(max(it.interest_due, 0)),
                                            from_paise(max(it.principal_due, 0))) for it in due_items])
                   if rest > 0 else [])
    ]
    # 2. The extra: principal of the installments being replaced, oldest first.
    left = to_paise(p.extra)
    for it in p.future:
        take = min(left, max(it.principal_due, 0))
        if take > 0:
            lines.append((it, 0, 0, take))
            left -= take
    payment = pay._post(ctx, loan, items, kind="payment", amount=data.amount, on=on, mode=data.mode,
                        reference=data.reference, note=None, key=data.idempotency_key, request_hash=request_hash,
                        lines=lines, fee_lines=fee_lines)
    # 3. Replace the installments not yet due by the new ones, on the same dates.
    for it in p.future:
        it.replaced = True
        it.settled = True
    next_seq = (db.scalar(select(func.max(ScheduleItem.seq)).where(ScheduleItem.loan_id == loan.id)) or 0) + 1
    balance = p.principal_before - p.extra
    new_items = []
    for k, ((pr, i), due) in enumerate(zip(p.result.parts, p.result.dates, strict=True)):
        balance -= pr
        new_items.append(ScheduleItem(loan_id=loan.id, seq=next_seq + k, due_date=due, installment=to_paise(pr + i),
                                      principal_part=to_paise(pr), interest_part=to_paise(i),
                                      closing_balance=to_paise(balance)))
    db.add_all(new_items)
    db.flush()
    current = [it for it in items if not it.replaced] + new_items
    replaced = [it for it in ledger.load_items(db, loan.id, include_replaced=True) if it.replaced]
    loan.installment_amount = to_paise(p.result.installment)
    loan.installments = len(current)
    loan.maturity_date = p.result.dates[-1]
    loan.total_interest = (sum(it.interest_part for it in current)
                           + sum(it.paid_interest + it.waived_interest for it in replaced))
    db.add(Reschedule(
        loan_id=loan.id, payment_id=payment.id, paid_on=on, extra=to_paise(p.extra), mode=data.mode_of_reschedule,
        old_installment=to_paise(summary["old_installment"]), new_installment=to_paise(p.result.installment),
        old_count=summary["old_count"], new_count=summary["new_count"], old_maturity=summary["old_maturity"],
        new_maturity=summary["new_maturity"], interest_saved=to_paise(p.interest_saved), created_by=ctx.user.id,
    ))
    ledger.refresh_loan_cache(loan, current)
    audit.from_ctx(ctx, "loan.prepaid", "loan", loan.id, {
        "loan_no": loan.loan_no, "receipt_no": payment.receipt_no, "amount": str(data.amount), "extra": str(p.extra),
        "mode": data.mode_of_reschedule, "new_installment": str(p.result.installment),
        "interest_saved": str(p.interest_saved),
    })
    db.commit()
    return payment
