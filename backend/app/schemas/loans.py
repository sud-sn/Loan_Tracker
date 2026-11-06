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
BrokenPeriodMode = Literal["none", "first_installment", "upfront"]
ChargeKind = Literal["processing_fee", "document_charges", "rto_stamp", "insurance", "other"]
ChargeTreatment = Literal["deducted", "added"]
VehicleType = Literal["two_wheeler", "three_wheeler", "car", "commercial", "tractor", "other"]
# Original documents (or keys) the lender keeps until the loan is closed.
Original = Literal[
    "rc_book", "duplicate_key", "insurance_copy", "blank_cheques", "promissory_note",
    "sale_deed", "patta", "ec", "parent_documents", "tax_receipt", "other",
]
SecurityKind = Literal["none", "vehicle", "land", "both"]


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
    # Round the regular installment up to a multiple of this: 0.01 (no rounding), 1, 5, 10, 50 or 100.
    # Reducing and flat loans only. The form starts from the owner's setting; the API default is none.
    emi_rounding: Decimal = Field(default=Decimal("0.01"), gt=0, max_digits=7, decimal_places=2)
    # Installments collected on the day the loan is given (reducing and flat loans only).
    advance_installments: int = Field(default=0, ge=0, le=12)
    # An odd first period: "first_installment" charges the actual days on the first installment,
    # "upfront" collects extra days' interest when the loan is given, "none" ignores it.
    broken_period: BrokenPeriodMode = "none"

    @model_validator(mode="after")
    def _needs(self) -> TermsIn:
        if self.method == "fixed_amount" and self.fixed_installment is None:
            raise ValueError("fixed_installment is required for a fixed amount")
        if self.method not in ("fixed_amount", "custom") and self.term_value is None:
            raise ValueError("term_value is required")
        if self.method == "custom" and not (self.custom_rows or self.custom_principal or self.term_value):
            raise ValueError("custom needs rows, a principal per installment, or a term")
        return self


class ChargeIn(Schema):
    """A charge collected when the loan is given: taken out of the amount handed over
    ("deducted") or added to the loan amount and repaid with it ("added")."""

    kind: ChargeKind
    label: str | None = Field(default=None, max_length=80)
    amount: PositiveMoney
    treatment: ChargeTreatment = "deducted"

    @model_validator(mode="after")
    def _label(self) -> ChargeIn:
        if self.kind == "other" and not (self.label or "").strip():
            raise ValueError("a label is required for another charge")
        return self


class SecurityIn(Schema):
    """The vehicle or land the loan is given against. ``value`` is the valuation used for the
    loan-to-value check; when it is missing, the on-road price (vehicle) or the market value,
    then the guideline value (land) is used."""

    kind: Literal["vehicle", "land"]
    value: PositiveMoney | None = None
    vehicle_type: VehicleType | None = None
    vehicle_condition: Literal["new", "used"] | None = None
    registration_no: str | None = Field(default=None, max_length=20)
    make_model: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=1950, le=2100)
    chassis_no: str | None = Field(default=None, max_length=40)
    engine_no: str | None = Field(default=None, max_length=40)
    on_road_price: PositiveMoney | None = None
    down_payment: Money | None = Field(default=None, ge=0)
    insurer: str | None = Field(default=None, max_length=80)
    insurance_policy_no: str | None = Field(default=None, max_length=60)
    insurance_expiry: date | None = None
    lien_noted_on_rc: bool = False
    survey_no: str | None = Field(default=None, max_length=60)
    patta_no: str | None = Field(default=None, max_length=40)
    extent: str | None = Field(default=None, max_length=40)
    village: str | None = Field(default=None, max_length=80)
    taluk: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    document_no: str | None = Field(default=None, max_length=60)
    sub_registrar_office: str | None = Field(default=None, max_length=80)
    guideline_value: PositiveMoney | None = None
    market_value: PositiveMoney | None = None
    ec_checked: bool = False
    ec_date: date | None = None
    originals_held: list[Original] = Field(default_factory=list, max_length=11)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _down_payment(self) -> SecurityIn:
        if self.down_payment and self.on_road_price and self.down_payment >= self.on_road_price:
            raise ValueError("the down payment must be less than the price")
        return self


class SecurityOut(SecurityIn):
    id: uuid.UUID
    version: int


class ChargeOut(Schema):
    kind: Literal["processing_fee", "document_charges", "rto_stamp", "insurance", "odd_period_interest", "other"]
    label: str | None
    amount: Money
    treatment: ChargeTreatment


class PreviewIn(TermsIn):
    """Terms plus what is collected when the loan is given and what it is given against, so the
    preview can show the amount handed over, the true cost and the loan-to-value check.
    ``principal`` is the loan amount before any charge added to it."""

    charges: list[ChargeIn] = Field(default_factory=list, max_length=10)
    security: list[SecurityIn] = Field(default_factory=list, max_length=5)


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
    first_installment: Money
    unrounded_installment: Money | None
    broken_period_days: int
    broken_period_interest: Money  # added to (negative: taken off) the first installment
    advance_installments: int
    advance_amount: Money
    loan_amount: Money  # as entered, before charges added to it
    charges_added: Money
    charges_deducted: Money  # includes extra days' interest collected up front
    odd_period_upfront: Money
    amount_handed_over: Money  # cash the borrower takes home on the day
    true_cost_monthly: Decimal | None  # % a month, reducing, including charges
    true_cost_yearly: Decimal | None
    security_value: Money | None
    ltv_percent: Decimal | None
    ltv_maximum: Decimal | None
    ltv_above_maximum: bool
    rows: list[ScheduleRowOut]


class LoanCreateIn(Schema):
    borrower_id: uuid.UUID
    terms: TermsIn
    charges: list[ChargeIn] = Field(default_factory=list, max_length=10)
    security: list[SecurityIn] = Field(default_factory=list, max_length=5)
    acknowledge_ltv_warning: bool = False
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
    status: Literal["upcoming", "due_today", "partially_paid", "overdue", "paid", "rescheduled"]


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
    fees_outstanding: Money
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
    emi_rounding: Decimal
    advance_installments: int
    broken_period: BrokenPeriodMode
    broken_period_days: int
    broken_period_interest: Money
    amount_handed_over: Money
    true_cost_monthly: Decimal | None
    security_kind: SecurityKind
    ltv_percent: Decimal | None
    charges: list[ChargeOut]
    security: list[SecurityOut]
    version: int
    created_at: datetime
    summary: LoanSummaryOut


FeeKind = Literal["bounce", "seizure", "legal", "valuation", "insurance", "foreclosure", "other"]


class FeeIn(Schema):
    kind: Literal["bounce", "seizure", "legal", "valuation", "insurance", "other"]
    label: str | None = Field(default=None, max_length=80)
    amount: PositiveMoney
    charged_on: date | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _label(self) -> FeeIn:
        if self.kind == "other" and not (self.label or "").strip():
            raise ValueError("a label is required for another charge")
        return self


class FeeOut(Schema):
    id: uuid.UUID
    kind: FeeKind
    label: str | None
    amount: Money
    charged_on: date
    paid: Money
    waived: Money
    due: Money
    waive_reason: str | None
    note: str | None


class WaiveIn(Schema):
    amount: PositiveMoney | None = None  # None = all that is due
    reason: str = Field(min_length=3, max_length=500)


class PrepayIn(Schema):
    amount: PositiveMoney
    paid_on: date | None = None
    mode_of_reschedule: Literal["reduce_emi", "reduce_term"] = "reduce_emi"
    mode: PaymentMode = "cash"
    reference: str | None = Field(default=None, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=80)


class PrepayPreviewOut(Schema):
    paid_on: date
    dues: Money  # charges, late fee and installments due by then, paid first
    extra: Money  # goes to principal
    principal_before: Money
    principal_after: Money
    old_installment: Money
    new_installment: Money
    old_count: int
    new_count: int
    old_maturity: date
    new_maturity: date
    interest_saved: Money
    rows: list[ScheduleRowOut]


class RescheduleOut(Schema):
    paid_on: date
    extra: Money
    mode: Literal["reduce_emi", "reduce_term"]
    old_installment: Money
    new_installment: Money
    old_count: int
    new_count: int
    old_maturity: date
    new_maturity: date
    interest_saved: Money


class LoanDetailOut(LoanOut):
    schedule: list[ScheduleItemOut]
    payments: list[PaymentOut]
    fees: list[FeeOut]
    reschedules: list[RescheduleOut]


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


Rebate = Literal["pro_rata", "rule_of_78", "none"]


class SettlementOut(Schema):
    on: date
    principal: Money
    interest: Money
    penalty: Money
    credit: Money
    interest_waived: Money
    rebate: Rebate
    charges: Money  # charges after the loan was given, still unpaid
    foreclosure_charge: Money
    foreclosure_percent: Decimal
    total: Money


class SettleIn(Schema):
    on: date | None = None
    expected_total: PositiveMoney
    rebate: Rebate = "pro_rata"
    # None = the % from Settings; 0 waives it; any other amount replaces it.
    foreclosure_charge: Money | None = Field(default=None, ge=0)
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
