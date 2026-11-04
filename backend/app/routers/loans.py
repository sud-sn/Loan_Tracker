from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from app.core import clock, i18n
from app.core.errors import AppError
from app.deps import CtxDep, LoanCreatorCtx, OwnerCtx, StepUpCtx
from app.models import Borrower, Loan, Payment
from app.schemas.common import Ok, Page
from app.schemas.loans import (
    LoanCreateIn,
    LoanDetailOut,
    LoanListItem,
    LoanUpdateIn,
    PaymentIn,
    PaymentOut,
    PreviewOut,
    ReminderOut,
    ReverseIn,
    SettleIn,
    SettlementOut,
    TermsIn,
    WriteOffIn,
)
from app.services import loans as service
from app.services import payments as payment_service
from app.services import pdf, reminders

router = APIRouter(tags=["loans"])


@router.post("/loans/preview", response_model=PreviewOut)
def preview(data: TermsIn, ctx: CtxDep) -> dict[str, Any]:
    result, above = service.preview(data, ctx.business)
    return service.preview_out(result, above, ctx.business)


@router.post("/loans", response_model=LoanDetailOut, status_code=201)
def create_loan(data: LoanCreateIn, ctx: LoanCreatorCtx) -> dict[str, Any]:
    loan = service.create(ctx, data)
    return service.serialize(ctx.db, service.get(ctx.db, loan.id), ctx.business, detail=True)


@router.get("/loans", response_model=Page[LoanListItem])
def list_loans(
    ctx: CtxDep,
    status: Literal["active", "closed", "written_off"] | None = None,
    borrower_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    stmt = select(Loan).join(Borrower, Borrower.id == Loan.borrower_id).where(Loan.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Loan.status == status)
    if borrower_id:
        stmt = stmt.where(Loan.borrower_id == borrower_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    loans = ctx.db.scalars(stmt.order_by(Loan.created_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    items = []
    for ln in loans:
        s = service.serialize(ctx.db, ln, ctx.business)
        items.append({
            "id": ln.id, "loan_no": ln.loan_no, "borrower": s["borrower"], "principal": s["principal"],
            "disbursal_date": ln.disbursal_date, "maturity_date": ln.maturity_date, "method": ln.method,
            "frequency": ln.frequency, "stored_status": ln.status, "status": s["summary"]["status"],
            "outstanding": s["summary"]["total_outstanding"], "overdue_amount": s["summary"]["overdue_amount"],
            "overdue_days": s["summary"]["overdue_days"],
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/loans/{loan_id}", response_model=LoanDetailOut)
def get_loan(loan_id: uuid.UUID, ctx: CtxDep) -> dict[str, Any]:
    return service.serialize(ctx.db, service.get(ctx.db, loan_id), ctx.business, detail=True)


@router.patch("/loans/{loan_id}", response_model=LoanDetailOut)
def update_loan(loan_id: uuid.UUID, data: LoanUpdateIn, ctx: CtxDep) -> dict[str, Any]:
    service.update(ctx, loan_id, data)
    return service.serialize(ctx.db, service.get(ctx.db, loan_id), ctx.business, detail=True)


@router.delete("/loans/{loan_id}", response_model=Ok)
def delete_loan(loan_id: uuid.UUID, ctx: OwnerCtx) -> Ok:
    service.soft_delete(ctx, loan_id)
    return Ok()


@router.get("/loans/{loan_id}/summary.pdf")
def loan_summary_pdf(loan_id: uuid.UUID, ctx: CtxDep, lang: Literal["en", "ta"] | None = None) -> Response:
    loan = service.get(ctx.db, loan_id)
    language = lang or ctx.lang
    data = service.serialize(ctx.db, loan, ctx.business, detail=True)
    body = pdf.render("loan_summary.html", language, ctx.business, loan=data,
                      borrower_name=i18n.name(language, loan.borrower.name_en, loan.borrower.name_ta))
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{loan.loan_no}.pdf"'})


@router.get("/loans/{loan_id}/reminder", response_model=ReminderOut)
def reminder(loan_id: uuid.UUID, ctx: CtxDep) -> dict[str, Any]:
    return reminders.for_loan(ctx.db, service.get(ctx.db, loan_id), ctx.business)


@router.post("/loans/{loan_id}/payments", response_model=PaymentOut, status_code=201)
def record_payment(
    loan_id: uuid.UUID, data: PaymentIn, ctx: CtxDep, response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if idempotency_key and idempotency_key != data.idempotency_key:
        raise AppError("IDEMPOTENCY_KEY_MISMATCH", 422)
    payment, replayed = payment_service.record(ctx, loan_id, data)
    if replayed:
        response.status_code = 200
    return {**payment_service.serialize(ctx.db, payment, with_balance=True), "replayed": replayed}


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, ctx: CtxDep) -> dict[str, Any]:
    payment = ctx.db.get(Payment, payment_id)
    if payment is None:
        raise AppError("PAYMENT_NOT_FOUND", 404)
    return payment_service.serialize(ctx.db, payment, with_balance=True)


@router.post("/payments/{payment_id}/reverse", response_model=PaymentOut)
def reverse_payment(payment_id: uuid.UUID, data: ReverseIn, ctx: StepUpCtx) -> dict[str, Any]:
    reversal = payment_service.reverse(ctx, payment_id, data.reason)
    return payment_service.serialize(ctx.db, reversal, with_balance=True)


@router.get("/payments/{payment_id}/receipt.pdf")
def receipt(payment_id: uuid.UUID, ctx: CtxDep, lang: Literal["en", "ta"] | None = None) -> Response:
    payment = ctx.db.get(Payment, payment_id)
    if payment is None:
        raise AppError("PAYMENT_NOT_FOUND", 404)
    loan = service.get(ctx.db, payment.loan_id)
    b = loan.borrower
    language = lang or b.preferred_language
    body = pdf.render("receipt.html", language, ctx.business, p=payment_service.serialize(ctx.db, payment,
                                                                                          with_balance=True),
                      b=b, loan=loan, borrower_name=i18n.name(language, b.name_en, b.name_ta), page_size="A5")
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{payment.receipt_no}.pdf"'})


@router.get("/loans/{loan_id}/settlement", response_model=SettlementOut)
def settlement(loan_id: uuid.UUID, ctx: CtxDep, on: date | None = None) -> dict[str, Any]:
    fig = payment_service.settlement_figure(ctx.db, service.get(ctx.db, loan_id), on or clock.today())
    return {k: getattr(fig, k) for k in ("on", "principal", "interest", "penalty", "credit", "total",
                                         "interest_waived")}


@router.post("/loans/{loan_id}/settle", response_model=PaymentOut)
def settle(loan_id: uuid.UUID, data: SettleIn, ctx: OwnerCtx) -> dict[str, Any]:
    payment = payment_service.settle(ctx, loan_id, data)
    return payment_service.serialize(ctx.db, payment, with_balance=True)


@router.post("/loans/{loan_id}/write-off", response_model=LoanDetailOut)
def write_off(loan_id: uuid.UUID, data: WriteOffIn, ctx: OwnerCtx) -> dict[str, Any]:
    payment_service.write_off(ctx, loan_id, data)
    return service.serialize(ctx.db, service.get(ctx.db, loan_id), ctx.business, detail=True)
