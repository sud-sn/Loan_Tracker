from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class RateBasis(StrEnum):
    MONTH = "month"
    YEAR = "year"


class TermUnit(StrEnum):
    MONTHS = "months"
    DAYS = "days"
    INSTALLMENTS = "installments"


class Frequency(StrEnum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    SINGLE = "single"


class Method(StrEnum):
    REDUCING = "reducing"  # EMI on reducing balance
    FLAT = "flat"  # same interest every installment, on the original principal
    INTEREST_ONLY = "interest_only"  # interest each period, principal at the end
    SIMPLE_DAYS = "simple_days"  # one payment at maturity, interest by days
    FIXED_AMOUNT = "fixed_amount"  # borrower pays a fixed amount; the app finds the period
    CUSTOM = "custom"  # lender sets principal and interest per installment


class FixedStyle(StrEnum):
    """How interest is worked out inside a fixed installment."""

    FLAT = "flat"  # same interest each time (on the original principal)
    REDUCING = "reducing"  # interest on the remaining balance


@dataclass(frozen=True)
class CustomRow:
    principal_part: Decimal
    interest_part: Decimal


@dataclass(frozen=True)
class LoanTerms:
    """Everything the engine needs to build a schedule.

    ``rate`` is a percentage (``Decimal("2")`` means 2 %).

    Method-specific inputs:

    * ``FIXED_AMOUNT`` needs ``fixed_installment``; ``term_value`` is ignored and the number
      of installments is the result. ``fixed_style`` picks flat or reducing interest.
    * ``CUSTOM`` takes either explicit ``custom_rows`` (one per installment, principal parts
      must add up to the principal), or ``custom_principal`` (and optional
      ``custom_interest``) to fill every row with the same split, or just a term to divide the
      principal equally. When ``custom_interest`` is missing it is principal x periodic rate.
    """

    principal: Decimal
    rate: Decimal
    rate_basis: RateBasis
    term_value: int | None
    term_unit: TermUnit
    frequency: Frequency
    method: Method
    disbursal_date: date
    first_due_date: date | None = None
    fixed_installment: Decimal | None = None
    fixed_style: FixedStyle = FixedStyle.FLAT
    custom_principal: Decimal | None = None
    custom_interest: Decimal | None = None
    custom_rows: tuple[CustomRow, ...] | None = field(default=None)
