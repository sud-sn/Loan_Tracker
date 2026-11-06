"""Payments, reversals, early settlement and write-off (PRD section 5).

A payment and its allocations are saved in one transaction while holding a row lock on the
loan, so two simultaneous payments cannot double-allocate. The ledger is append-only.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.deps import Ctx
from app.engine import from_paise, q2, to_paise
from app.engine.allocation import OpenItem, allocate
from app.engine.settlement import Rebate, Settlement, SettlementItem, settlement
from app.models import (
    BusinessSettings,
    FeeAllocation,
    Loan,
    LoanAdjustment,
    LoanFee,
    Payment,
    PaymentAllocation,
    ScheduleItem,
)
from app.repositories import counters
from app.schemas.loans import PaymentIn, SettleIn, WriteOffIn
from app.security.tokens import now
from app.services import audit, ledger


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _replay(db: Session, key: str, request_hash: str) -> Payment | None:
    existing = db.scalars(select(Payment).where(Payment.idempotency_key == key)).first()
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise AppError("IDEMPOTENCY_KEY_REUSED", 409)
    return existing


def _active_loan(db: Session, loan_id: uuid.UUID) -> Loan:
    loan = ledger.lock_loan(db, loan_id)
    if loan is None:
        raise AppError("LOAN_NOT_FOUND", 404)
    if loan.status != "active":
        raise AppError("LOAN_NOT_ACTIVE", 409, status=loan.status)
    return loan


def _check_date(loan: Loan, on: date) -> None:
    if on > clock.today():
        raise AppError("DATE_IN_FUTURE", 422)
    if on < loan.disbursal_date:
        raise AppError("DATE_BEFORE_DISBURSAL", 422)


def _fee_lines(fees: list[LoanFee], amount: int, on: date) -> list[tuple[LoanFee, int]]:
    """Charges are paid first, oldest first (only those charged on or before the payment date)."""
    lines: list[tuple[LoanFee, int]] = []
    left = amount
    for fee in fees:
        if left <= 0:
            break
        if fee.charged_on <= on and fee.due > 0:
            take = min(left, fee.due)
            lines.append((fee, take))
            left -= take
    return lines


def _maybe_close(db: Session, loan: Loan, items: list[ScheduleItem], on: date, reason: str) -> None:
    if all(it.settled for it in items) and ledger.fees_due(ledger.load_fees(db, loan.id)) <= 0:
        pen = ledger.penalty_due(db, loan, items, clock.today())
        if all(v <= 0 for v in pen.values()):
            loan.status = "closed"
            loan.closed_at = now()
            loan.closed_on = on
            loan.closed_reason = reason


def _post(
    ctx: Ctx, loan: Loan, items: list[ScheduleItem], *, kind: str, amount: Decimal, on: date, mode: str,
    reference: str | None, note: str | None, key: str, request_hash: str,
    lines: list[tuple[ScheduleItem, int, int, int]], fee_lines: list[tuple[LoanFee, int]] | None = None,
) -> Payment:
    payment = Payment(
        receipt_no=counters.next_receipt_no(ctx.db, on.year), loan_id=loan.id, kind=kind,
        amount=to_paise(amount), paid_on=on, mode=mode, reference=reference, note=note,
        idempotency_key=key, request_hash=request_hash, created_by=ctx.user.id,
    )
    ctx.db.add(payment)
    ctx.db.flush()
    for item, pen, intr, prin in lines:
        ctx.db.add(PaymentAllocation(payment_id=payment.id, schedule_item_id=item.id, penalty_part=pen,
                                     interest_part=intr, principal_part=prin))
        ledger.apply_to_item(item, pen, intr, prin)
    for fee, amount_paid in fee_lines or []:
        ctx.db.add(FeeAllocation(payment_id=payment.id, fee_id=fee.id, amount=amount_paid))
        fee.paid += amount_paid
    if loan.last_payment_on is None or on > loan.last_payment_on:
        loan.last_payment_on = on
    ledger.refresh_loan_cache(loan, items)
    return payment


def record(ctx: Ctx, loan_id: uuid.UUID, data: PaymentIn, *, commit: bool = True) -> tuple[Payment, bool]:
    db = ctx.db
    on = data.paid_on or clock.today()
    request_hash = _request_hash({"loan": str(loan_id), "amount": str(data.amount), "on": on.isoformat(),
                                  "mode": data.mode, "ref": data.reference, "note": data.note})
    if (hit := _replay(db, data.idempotency_key, request_hash)) is not None:
        return hit, True
    loan = _active_loan(db, loan_id)
    # Re-check under the lock: a concurrent request with the same key may just have committed.
    if (hit := _replay(db, data.idempotency_key, request_hash)) is not None:
        db.rollback()
        return hit, True
    _check_date(loan, on)
    items = ledger.load_items(db, loan.id, lock=True)
    fees = ledger.load_fees(db, loan.id, lock=True)
    pen = ledger.penalty_due(db, loan, items, on)
    by_id = {str(it.id): it for it in items}
    open_items = [
        OpenItem(str(it.id), it.seq, pen[it.id], from_paise(max(it.interest_due, 0)),
                 from_paise(max(it.principal_due, 0)))
        for it in items
    ]
    fee_lines = _fee_lines(fees, to_paise(data.amount), on)
    rest = data.amount - from_paise(sum(a for _, a in fee_lines))
    lines = allocate(rest, open_items) if rest > 0 else []
    payment = _post(
        ctx, loan, items, kind="payment", amount=data.amount, on=on, mode=data.mode, reference=data.reference,
        note=data.note, key=data.idempotency_key, request_hash=request_hash,
        lines=[(by_id[ln.item_id], to_paise(ln.penalty_part), to_paise(ln.interest_part),
                to_paise(ln.principal_part)) for ln in lines],
        fee_lines=fee_lines,
    )
    _maybe_close(db, loan, items, on, "paid")
    audit.from_ctx(ctx, "payment.recorded", "payment", payment.id, {
        "receipt_no": payment.receipt_no, "loan_no": loan.loan_no, "amount": str(data.amount),
        "paid_on": on.isoformat(), "mode": data.mode,
    })
    if not commit:
        db.flush()
        return payment, False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if (hit := _replay(db, data.idempotency_key, request_hash)) is not None:
            return hit, True
        raise
    return payment, False


def reverse(ctx: Ctx, payment_id: uuid.UUID, reason: str) -> Payment:
    db = ctx.db
    original = db.get(Payment, payment_id)
    if original is None:
        raise AppError("PAYMENT_NOT_FOUND", 404)
    if original.kind != "payment":
        raise AppError("PAYMENT_NOT_REVERSIBLE", 409, kind=original.kind)
    loan = ledger.lock_loan(db, original.loan_id)
    if loan is None:
        raise AppError("LOAN_NOT_FOUND", 404)
    if loan.status == "written_off":
        raise AppError("LOAN_NOT_ACTIVE", 409, status=loan.status)
    if db.scalars(select(Payment).where(Payment.reversed_of_id == original.id)).first():
        raise AppError("ALREADY_REVERSED", 409)
    items = {it.id: it for it in ledger.load_items(db, loan.id, lock=True)}
    allocations = db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == original.id)).all()
    if any(a.schedule_item_id not in items for a in allocations):
        # Part of it sits on installments a part-prepayment has since replaced: undoing it would
        # break the new schedule. Record a correction as a new entry instead.
        raise AppError("PAYMENT_LOCKED_BY_RESCHEDULE", 409)
    fee_allocations = db.scalars(select(FeeAllocation).where(FeeAllocation.payment_id == original.id)).all()
    fees = {f.id: f for f in ledger.load_fees(db, loan.id, lock=True)}
    today = clock.today()
    reversal = Payment(
        receipt_no=counters.next_receipt_no(db, today.year), loan_id=loan.id, kind="reversal",
        amount=original.amount, paid_on=today, mode=original.mode, reference=original.receipt_no,
        idempotency_key=f"reversal:{original.id}", request_hash=_request_hash({"reverse": str(original.id)}),
        reversed_of_id=original.id, reversal_reason=reason, created_by=ctx.user.id,
    )
    db.add(reversal)
    db.flush()
    for a in allocations:
        db.add(PaymentAllocation(payment_id=reversal.id, schedule_item_id=a.schedule_item_id,
                                 penalty_part=-a.penalty_part, interest_part=-a.interest_part,
                                 principal_part=-a.principal_part))
        ledger.apply_to_item(items[a.schedule_item_id], -a.penalty_part, -a.interest_part, -a.principal_part)
    for fa in fee_allocations:
        db.add(FeeAllocation(payment_id=reversal.id, fee_id=fa.fee_id, amount=-fa.amount))
        fees[fa.fee_id].paid -= fa.amount
    db.flush()
    loan.last_payment_on = ledger.last_payment_on(db, loan.id)
    ledger.refresh_loan_cache(loan, list(items.values()))
    if loan.status == "closed":
        loan.status, loan.closed_at, loan.closed_on, loan.closed_reason = "active", None, None, None
    audit.from_ctx(ctx, "payment.reversed", "payment", original.id, {
        "receipt_no": original.receipt_no, "reversal_receipt_no": reversal.receipt_no,
        "amount": str(from_paise(original.amount)), "reason": reason,
    })
    db.commit()
    return reversal


def _settlement_items(db: Session, loan: Loan, items: list[ScheduleItem], on: date) -> list[SettlementItem]:
    pen = ledger.penalty_due(db, loan, items, on)
    out: list[SettlementItem] = []
    previous = loan.disbursal_date
    for it in items:
        out.append(SettlementItem(
            item_id=str(it.id), seq=it.seq, period_start=previous, due_date=it.due_date,
            principal_part=from_paise(it.principal_part), interest_part=from_paise(it.interest_part),
            principal_paid=from_paise(it.paid_principal), interest_paid=from_paise(it.paid_interest),
            penalty_due=pen[it.id], waived_interest=from_paise(it.waived_interest),
            waived_principal=from_paise(it.waived_principal),
        ))
        previous = it.due_date
    return out


@dataclass(frozen=True)
class Closing:
    """What closing the loan early costs on a date: the schedule part, charges still unpaid, and
    the foreclosure charge (a % of the principal being repaid, which the owner can change)."""

    fig: Settlement
    rebate: Rebate
    fees: Decimal
    foreclosure: Decimal
    foreclosure_percent: Decimal

    @property
    def total(self) -> Decimal:
        return self.fig.total + self.fees + self.foreclosure


def closing_figure(db: Session, loan: Loan, items: list[ScheduleItem], fees: list[LoanFee], on: date,
                   business: BusinessSettings, rebate: Rebate = Rebate.PRO_RATA,
                   foreclosure: Decimal | None = None) -> Closing:
    _check_date(loan, on)
    if loan.last_payment_on and on < loan.last_payment_on:
        raise AppError("DATE_BEFORE_LAST_PAYMENT", 422)
    fig = settlement(_settlement_items(db, loan, items, on), on, rebate)
    percent = Decimal(business.foreclosure_charge_percent)
    charge = q2(fig.principal * percent / 100) if foreclosure is None else q2(foreclosure)
    return Closing(fig, rebate, from_paise(ledger.fees_due(fees)), charge, percent)


def settlement_figure(db: Session, loan: Loan, on: date, business: BusinessSettings,
                      rebate: Rebate = Rebate.PRO_RATA, foreclosure: Decimal | None = None) -> Closing:
    return closing_figure(db, loan, ledger.load_items(db, loan.id), ledger.load_fees(db, loan.id), on, business,
                          rebate, foreclosure)


def settle(ctx: Ctx, loan_id: uuid.UUID, data: SettleIn) -> Payment:
    db = ctx.db
    on = data.on or clock.today()
    request_hash = _request_hash({"settle": str(loan_id), "on": on.isoformat(), "total": str(data.expected_total),
                                  "rebate": data.rebate, "foreclosure": str(data.foreclosure_charge)})
    if (hit := _replay(db, data.idempotency_key, request_hash)) is not None:
        return hit
    loan = _active_loan(db, loan_id)
    items = ledger.load_items(db, loan.id, lock=True)
    fees = ledger.load_fees(db, loan.id, lock=True)
    closing = closing_figure(db, loan, items, fees, on, ctx.business, Rebate(data.rebate), data.foreclosure_charge)
    fig = closing.fig
    if closing.total != data.expected_total:
        raise AppError("SETTLEMENT_CHANGED", 409, total=str(closing.total))
    if closing.foreclosure > 0:
        fee = LoanFee(loan_id=loan.id, kind="foreclosure", amount=to_paise(closing.foreclosure), charged_on=on,
                      created_by=ctx.user.id)
        db.add(fee)
        db.flush()
        fees.append(fee)
    by_id = {str(it.id): it for it in items}
    payment = _post(
        ctx, loan, items, kind="settlement", amount=closing.total, on=on, mode=data.mode, reference=data.reference,
        note=None, key=data.idempotency_key, request_hash=request_hash,
        lines=[(by_id[ln.item_id], to_paise(ln.penalty), to_paise(ln.interest), to_paise(ln.principal))
               for ln in fig.lines if ln.penalty or ln.interest or ln.principal],
        fee_lines=[(f, f.due) for f in fees if f.due > 0],
    )
    for ln in fig.lines:
        if ln.interest_waived or ln.principal_waived:
            item = by_id[ln.item_id]
            db.add(LoanAdjustment(
                loan_id=loan.id, schedule_item_id=item.id, payment_id=payment.id, kind="settlement_waiver",
                adjusted_on=on, interest_part=to_paise(ln.interest_waived),
                principal_part=to_paise(ln.principal_waived), reason="early settlement", created_by=ctx.user.id,
            ))
            ledger.waive_on_item(item, 0, to_paise(ln.interest_waived), to_paise(ln.principal_waived))
    ledger.refresh_loan_cache(loan, items)
    loan.status, loan.closed_at, loan.closed_on, loan.closed_reason = "closed", now(), on, "settled_early"
    audit.from_ctx(ctx, "loan.settled", "loan", loan.id, {
        "loan_no": loan.loan_no, "total": str(closing.total), "interest_waived": str(fig.interest_waived),
        "rebate": data.rebate, "foreclosure_charge": str(closing.foreclosure), "charges": str(closing.fees),
        "receipt_no": payment.receipt_no,
    })
    db.commit()
    return payment


def write_off(ctx: Ctx, loan_id: uuid.UUID, data: WriteOffIn) -> Loan:
    db = ctx.db
    today = clock.today()
    loan = _active_loan(db, loan_id)
    items = ledger.load_items(db, loan.id, lock=True)
    if data.amount_received:
        request_hash = _request_hash({"writeoff": str(loan_id), "amount": str(data.amount_received)})
        if _replay(db, data.idempotency_key, request_hash) is not None:
            raise AppError("ALREADY_DONE", 409)
        pen = ledger.penalty_due(db, loan, items, today)
        by_id = {str(it.id): it for it in items}
        lines = allocate(data.amount_received, [
            OpenItem(str(it.id), it.seq, pen[it.id], from_paise(max(it.interest_due, 0)),
                     from_paise(max(it.principal_due, 0))) for it in items
        ])
        _post(ctx, loan, items, kind="payment", amount=data.amount_received, on=today, mode=data.mode,
              reference=None, note=f"settlement for less: {data.reason}", key=data.idempotency_key,
              request_hash=request_hash,
              lines=[(by_id[ln.item_id], to_paise(ln.penalty_part), to_paise(ln.interest_part),
                      to_paise(ln.principal_part)) for ln in lines])
        db.flush()
    pen = ledger.penalty_due(db, loan, items, today)
    written = 0
    for it in items:
        p, i, n = max(it.principal_due, 0), max(it.interest_due, 0), to_paise(pen[it.id])
        if p or i or n:
            db.add(LoanAdjustment(loan_id=loan.id, schedule_item_id=it.id, kind="write_off", adjusted_on=today,
                                  principal_part=p, interest_part=i, penalty_part=n, reason=data.reason,
                                  created_by=ctx.user.id))
            ledger.waive_on_item(it, n, i, p)
            written += p + i + n
    ledger.refresh_loan_cache(loan, items)
    loan.status, loan.closed_at, loan.closed_on, loan.closed_reason = "written_off", now(), today, data.reason
    audit.from_ctx(ctx, "loan.written_off", "loan", loan.id, {
        "loan_no": loan.loan_no, "reason": data.reason, "written_off": str(from_paise(written)),
        "amount_received": str(data.amount_received or 0),
    })
    db.commit()
    return loan


def serialize(db: Session, payment: Payment, *, with_balance: bool = False) -> dict[str, Any]:
    rows = db.execute(
        select(PaymentAllocation, ScheduleItem.seq, ScheduleItem.due_date)
        .join(ScheduleItem, ScheduleItem.id == PaymentAllocation.schedule_item_id)
        .where(PaymentAllocation.payment_id == payment.id)
        .order_by(ScheduleItem.seq)
    ).all()
    allocations: list[dict[str, Any]] = [
        {"seq": seq, "due_date": due, "penalty_part": from_paise(a.penalty_part),
         "interest_part": from_paise(a.interest_part), "principal_part": from_paise(a.principal_part)}
        for a, seq, due in rows
    ]
    reversed_by = db.scalar(select(Payment.id).where(Payment.reversed_of_id == payment.id))
    out: dict[str, Any] = {
        "id": payment.id, "receipt_no": payment.receipt_no, "loan_id": payment.loan_id, "kind": payment.kind,
        "amount": from_paise(payment.amount), "paid_on": payment.paid_on, "mode": payment.mode,
        "reference": payment.reference, "note": payment.note, "reversed_of_id": payment.reversed_of_id,
        "reversal_reason": payment.reversal_reason, "reversed_by_id": reversed_by,
        "created_at": payment.created_at, "allocations": allocations,
        "penalty_total": sum((a["penalty_part"] for a in allocations), Decimal("0.00")),
        "interest_total": sum((a["interest_part"] for a in allocations), Decimal("0.00")),
        "principal_total": sum((a["principal_part"] for a in allocations), Decimal("0.00")),
    }
    if with_balance:
        out["balance_after"] = balance_after(db, payment)
    return out


def balance_after(db: Session, payment: Payment) -> Decimal:
    """Unpaid principal + interest on the loan right after this payment was saved."""
    from sqlalchemy import func

    scheduled = db.scalar(select(func.sum(ScheduleItem.installment)).where(ScheduleItem.loan_id == payment.loan_id))
    paid = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.principal_part + PaymentAllocation.interest_part), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.loan_id == payment.loan_id, Payment.created_at <= payment.created_at)
    )
    waived = db.scalar(
        select(func.coalesce(func.sum(LoanAdjustment.principal_part + LoanAdjustment.interest_part), 0))
        .where(LoanAdjustment.loan_id == payment.loan_id, LoanAdjustment.created_at <= payment.created_at)
    )
    return from_paise(max(int(scheduled or 0) - int(paid or 0) - int(waived or 0), 0))
