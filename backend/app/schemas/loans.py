from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import Money, PaymentMode, PositiveMoney, Schema

Method = Literal["reducing", "flat", "interest_only", "simple_days", "fixed_amount", "custom"]
Frequency = Literal["monthly", "weekly", "daily", "single"]
TermUnit = Literal["months", "days", "installments"]
RateBasis = Literal["month", "year"]
PenaltyMode = Literal["off", "per_day", "pct_month"]


class CustomRowIn(Schema):
    principal_part: Money = Field(ge=0)
    interest_part: Money = Field(ge=0)


class TermsIn(Schema):
    """Loan terms as the lender enters them.

    Fixed amount every installment (``method="fixed_amount"``): give ``fixed_installment``;
    the app works out how many installments are needed. ``fixed_style`` says whether the
    interest inside each payment is the same every time (flat) or on the remaining balance.

    Set the split yourself (``method="custom"``): give ``custom_principal`` and optionally
    ``custom_interest`` per installment (the period is worked out), or a term to split the
    principal equally, or ``custom_rows`` with one row per installment.
    """

    principal: PositiveMoney
    rate: Decimal = Field(ge=0, le=100, max_digits=9, decimal_places=4)
    rate_basis: RateBasis = "month"
    term_value: int | None = Field(default=None, ge=1, le=3660)
    term_unit: TermUnit = "months"
    frequency: Frequency = "monthly"
    method: Method = "reducing"
    disbursal_date: date
    first_due_date: date | None = None
    fixed_installment: PositiveMoney | None = None
    fixed_style: Literal["flat", "reducing"] = "flat"
    custom_principal: PositiveMoney | None = None
    custom_interest: Money | None = Field(default=None, ge=0)
    custom_rows: list[CustomRowIn] | None = Field(default=None, max_length=3660)

    @model_validator(mode="after")
    def _needs(self) -> TermsIn:
        if self.method == "fixed_amount" and self.fixed_installment is None:
            raise ValueError("fixed_installment is required for a fixed amount")
        if self.method not in ("fixed_amount", "custom") and self.term_value is None:
            raise ValueError("term_value is required")
        if self.method == "custom" and not (self.custom_rows or self.custom_principal or self.term_value):
            raise ValueError("custom needs rows, a principal per installment, or a term")
        return self


class PenaltyIn(Schema):
    mode: PenaltyMode = "off"
    value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=4)
    grace_days: int = Field(default=0, ge=0, le=365)


class ScheduleRowOut(Schema):
    seq: int
    due_date: date
    installment: Money
    principal_part: Money
    interest_part: Money
    closing_balance: Money


class PreviewOut(Schema):
    installment: Money
    last_installment: Money
    total_principal: Money
    total_interest: Money
    total_payable: Money
    installments: int
    first_due_date: date
    maturity_date: date
    monthly_rate_equivalent: Decimal
    rate_above_maximum: bool
    max_rate_monthly: Decimal | None
    rows: list[ScheduleRowOut]


class LoanCreateIn(Schema):
    borrower_id: uuid.UUID
    terms: TermsIn
    penalty: PenaltyIn = PenaltyIn()
    disbursal_mode: PaymentMode = "cash"
    purpose: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)
    acknowledge_rate_warning: bool = False
    idempotency_key: str = Field(min_length=8, max_length=80)


class LoanUpdateIn(Schema):
    version: int
    purpose: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class AllocationOut(Schema):
    seq: int
    due_date: date
    penalty_part: Money
    interest_part: Money
    principal_part: Money


class PaymentOut(Schema):
    id: uuid.UUID
    receipt_no: str
    loan_id: uuid.UUID
    kind: Literal["payment", "reversal", "settlement"]
    amount: Money
    paid_on: date
    mode: PaymentMode
    reference: str | None
    note: str | None
    reversed_of_id: uuid.UUID | None
    reversal_reason: str | None
    reversed_by_id: uuid.UUID | None = None
    created_at: datetime
    allocations: list[AllocationOut]
    penalty_total: Money
    interest_total: Money
    principal_total: Money
    balance_after: Money | None = None
    replayed: bool = False


class ScheduleItemOut(Schema):
    id: uuid.UUID
    seq: int
    due_date: date
    installment: Money
    principal_part: Money
    interest_part: Money
    closing_balance: Money
    paid_principal: Money
    paid_interest: Money
    paid_penalty: Money
    waived: Money
    penalty_due: Money
    unpaid: Money
    status: Literal["upcoming", "due_today", "partially_paid", "overdue", "paid"]


class LoanSummaryOut(Schema):
    status: Literal["active", "due_soon", "overdue", "closed", "written_off"]
    overdue_days: int
    overdue_amount: Money
    overdue_installments: int
    due_today_amount: Money
    next_due_date: date | None
    next_due_amount: Money
    principal_outstanding: Money
    interest_outstanding: Money
    penalty_outstanding: Money
    total_outstanding: Money
    days_since_last_payment: int
    paid_total: Money


class BorrowerRef(Schema):
    id: uuid.UUID
    code: str
    name_en: str | None
    name_ta: str | None
    phone: str | None
    preferred_language: Literal["en", "ta"]


class LoanOut(Schema):
    id: uuid.UUID
    loan_no: str
    borrower: BorrowerRef
    principal: Money
    rate: Decimal
    rate_basis: RateBasis
    term_value: int | None
    term_unit: TermUnit
    frequency: Frequency
    method: Method
    fixed_style: Literal["flat", "reducing"] | None
    fixed_installment: Money | None
    installments: int
    installment_amount: Money
    total_interest: Money
    disbursal_date: date
    first_due_date: date
    maturity_date: date
    disbursal_mode: PaymentMode
    penalty_mode: PenaltyMode
    penalty_value: Decimal
    penalty_grace_days: int
    stored_status: Literal["active", "closed", "written_off"]
    closed_on: date | None
    closed_reason: str | None
    last_payment_on: date | None
    purpose: str | None
    notes: str | None
    version: int
    created_at: datetime
    summary: LoanSummaryOut


class LoanDetailOut(LoanOut):
    schedule: list[ScheduleItemOut]
    payments: list[PaymentOut]


class LoanListItem(Schema):
    id: uuid.UUID
    loan_no: str
    borrower: BorrowerRef
    principal: Money
    disbursal_date: date
    maturity_date: date
    method: Method
    frequency: Frequency
    stored_status: str
    status: str
    outstanding: Money
    overdue_amount: Money
    overdue_days: int


class PaymentIn(Schema):
    amount: PositiveMoney
    paid_on: date | None = None
    mode: PaymentMode = "cash"
    reference: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=80)


class ReverseIn(Schema):
    reason: str = Field(min_length=3, max_length=500)


class SettlementOut(Schema):
    on: date
    principal: Money
    interest: Money
    penalty: Money
    credit: Money
    total: Money
    interest_waived: Money


class SettleIn(Schema):
    on: date | None = None
    expected_total: PositiveMoney
    mode: PaymentMode = "cash"
    reference: str | None = Field(default=None, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=80)


class WriteOffIn(Schema):
    reason: str = Field(min_length=3, max_length=500)
    amount_received: PositiveMoney | None = None
    mode: PaymentMode = "cash"
    idempotency_key: str = Field(min_length=8, max_length=80)


class ReminderOut(Schema):
    phone: str | None
    language: Literal["en", "ta"]
    message: str
    whatsapp_url: str | None
    tel_url: str | None
