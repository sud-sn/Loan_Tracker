"""Repayment schedule builder (PRD section 4, plus the fixed-amount and custom methods).

Rules enforced for every method:

* money is ``Decimal`` and every part is rounded half-up to 2 decimals;
* the last installment absorbs rounding, so principal parts add up to the principal exactly;
* monthly due dates keep the first due day, clamped to the end of short months.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext

from app.engine.dates import add_months, due_dates, one_period_after
from app.engine.errors import EngineError
from app.engine.money import ZERO, q2
from app.engine.types import CustomRow, FixedStyle, Frequency, LoanTerms, Method, RateBasis, TermUnit

MAX_INSTALLMENTS = 3660  # ten years of daily collection
MAX_PRINCIPAL = Decimal("100000000000")  # ₹1,000 crore: anything above is a typo
MAX_RATE_PERCENT = Decimal("100")
# With a fixed installment, a leftover below ₹1 is folded into the previous payment instead of
# creating an extra installment of a few paise.
ABSORB_BELOW = Decimal("1.00")


@dataclass(frozen=True)
class ScheduleRow:
    seq: int
    due_date: date
    installment: Decimal
    principal_part: Decimal
    interest_part: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class ScheduleResult:
    rows: tuple[ScheduleRow, ...]
    installment: Decimal  # the regular installment (first row)
    last_installment: Decimal
    total_principal: Decimal
    total_interest: Decimal
    total_payable: Decimal
    installments: int
    first_due_date: date
    maturity_date: date
    periodic_rate: Decimal  # fraction per installment period
    monthly_rate_equivalent: Decimal  # % per month, used for the maximum-rate warning


def periodic_rate(rate_percent: Decimal, basis: RateBasis, frequency: Frequency) -> Decimal:
    """Interest rate per installment period, as a fraction.

    A monthly rate gives one day = rate / 30 (PRD section 16); a yearly rate gives one day =
    rate / 365 and one month = rate / 12. A week is seven days.
    """
    r = rate_percent / Decimal(100)
    if frequency is Frequency.MONTHLY:
        return r if basis is RateBasis.MONTH else r / 12
    if frequency is Frequency.WEEKLY:
        return r * 7 / 30 if basis is RateBasis.MONTH else r * 7 / 365
    if frequency is Frequency.DAILY:
        return r / 30 if basis is RateBasis.MONTH else r / 365
    # SINGLE: the per-day rate is applied by the simple-interest method itself.
    return r / 30 if basis is RateBasis.MONTH else r / 365


def installment_count(terms: LoanTerms) -> int:
    """Number of installments from the term (not used by FIXED_AMOUNT, which solves for it)."""
    if terms.frequency is Frequency.SINGLE:
        return 1
    value = terms.term_value
    if value is None or value <= 0:
        raise EngineError("TERM_INVALID")
    unit, freq = terms.term_unit, terms.frequency
    if unit is TermUnit.INSTALLMENTS:
        n = value
    elif freq is Frequency.MONTHLY:
        n = value if unit is TermUnit.MONTHS else math.ceil(value / 30)
    elif freq is Frequency.WEEKLY:
        n = math.ceil((value if unit is TermUnit.DAYS else value * 30) / 7)
    else:  # DAILY
        n = value if unit is TermUnit.DAYS else value * 30
    if n > MAX_INSTALLMENTS:
        raise EngineError("TERM_TOO_LONG", max=MAX_INSTALLMENTS)
    return n


def _validate(terms: LoanTerms) -> None:
    if terms.principal <= 0 or terms.principal > MAX_PRINCIPAL:
        raise EngineError("PRINCIPAL_INVALID")
    if terms.principal != q2(terms.principal):
        raise EngineError("AMOUNT_TOO_MANY_DECIMALS")
    if terms.rate < 0 or terms.rate > MAX_RATE_PERCENT:
        raise EngineError("RATE_INVALID")
    if terms.method is Method.INTEREST_ONLY and terms.rate == 0:
        raise EngineError("RATE_REQUIRED_FOR_METHOD")
    single_methods = {Method.SIMPLE_DAYS}
    if (terms.frequency is Frequency.SINGLE) != (terms.method in single_methods):
        raise EngineError("FREQUENCY_METHOD_MISMATCH")
    if terms.first_due_date is not None and terms.first_due_date <= terms.disbursal_date:
        raise EngineError("FIRST_DUE_NOT_AFTER_DISBURSAL")


def _make_rows(
    principal: Decimal, dates: list[date], parts: list[tuple[Decimal, Decimal]]
) -> tuple[ScheduleRow, ...]:
    rows: list[ScheduleRow] = []
    balance = principal
    for seq, (due, (p, i)) in enumerate(zip(dates, parts, strict=True), start=1):
        if p < 0 or i < 0:
            raise EngineError("SCHEDULE_ROW_NEGATIVE", seq=seq)
        if p + i <= 0:
            raise EngineError("SCHEDULE_ROW_EMPTY", seq=seq)
        balance -= p
        rows.append(ScheduleRow(seq, due, p + i, p, i, balance))
    if balance != ZERO:  # pragma: no cover - guarded by every builder below
        raise EngineError("PRINCIPAL_SUM_MISMATCH")
    return tuple(rows)


def _reducing_parts(principal: Decimal, r: Decimal, n: int) -> list[tuple[Decimal, Decimal]]:
    if r == 0:
        installment = q2(principal / n)
    else:
        growth = (1 + r) ** n
        installment = q2(principal * r * growth / (growth - 1))
    parts: list[tuple[Decimal, Decimal]] = []
    balance = principal
    for k in range(1, n + 1):
        interest = q2(balance * r)
        p = balance if k == n else min(installment - interest, balance)
        parts.append((p, interest))
        balance -= p
    return parts


def _equal_split(total: Decimal, n: int) -> list[Decimal]:
    """Split ``total`` into ``n`` equal rounded parts; the last part absorbs rounding.

    If half-up rounding would push the last part below zero (only possible for tiny totals
    over many installments), fall back to cumulative rounding, which never goes negative.
    """
    each = q2(total / n)
    last = total - each * (n - 1)
    if last >= 0:
        return [each] * (n - 1) + [last]
    cumulative = [q2(total * k / n) for k in range(n + 1)]
    return [cumulative[k + 1] - cumulative[k] for k in range(n)]


def _flat_parts(principal: Decimal, r: Decimal, n: int) -> list[tuple[Decimal, Decimal]]:
    total_interest = q2(principal * r * n)
    return list(zip(_equal_split(principal, n), _equal_split(total_interest, n), strict=True))


def _interest_only_parts(principal: Decimal, r: Decimal, n: int) -> list[tuple[Decimal, Decimal]]:
    interest = q2(principal * r)
    return [(ZERO, interest)] * (n - 1) + [(principal, interest)]


def _fill_fixed_principal(
    principal: Decimal, p_each: Decimal, interest_each: Decimal
) -> list[tuple[Decimal, Decimal]]:
    if p_each <= 0:
        raise EngineError("INSTALLMENT_TOO_SMALL")
    n = math.ceil(principal / p_each)
    if n > 1 and principal - p_each * (n - 1) < ABSORB_BELOW:
        n -= 1
    if n > MAX_INSTALLMENTS:
        raise EngineError("TERM_TOO_LONG", max=MAX_INSTALLMENTS)
    parts = [(p_each, interest_each)] * (n - 1)
    parts.append((principal - p_each * (n - 1), interest_each))
    return parts


def _fixed_amount_parts(
    principal: Decimal, r: Decimal, amount: Decimal, style: FixedStyle
) -> list[tuple[Decimal, Decimal]]:
    """The borrower pays ``amount`` every period; the last payment is whatever is left."""
    if amount <= 0 or amount != q2(amount):
        raise EngineError("INSTALLMENT_INVALID")
    if style is FixedStyle.FLAT:
        interest = q2(principal * r)
        if amount <= interest:
            raise EngineError("INSTALLMENT_TOO_SMALL", minimum=str(interest + Decimal("0.01")))
        return _fill_fixed_principal(principal, amount - interest, interest)
    parts: list[tuple[Decimal, Decimal]] = []
    balance = principal
    while balance > 0:
        interest = q2(balance * r)
        if amount <= interest:
            raise EngineError("INSTALLMENT_TOO_SMALL", minimum=str(interest + Decimal("0.01")))
        p = balance if balance - (amount - interest) < ABSORB_BELOW else amount - interest
        parts.append((p, interest))
        balance -= p
        if len(parts) > MAX_INSTALLMENTS:
            raise EngineError("TERM_TOO_LONG", max=MAX_INSTALLMENTS)
    return parts


def _custom_parts(terms: LoanTerms, r: Decimal) -> list[tuple[Decimal, Decimal]]:
    principal = terms.principal
    if terms.custom_rows:
        rows: tuple[CustomRow, ...] = terms.custom_rows
        if len(rows) > MAX_INSTALLMENTS:
            raise EngineError("TERM_TOO_LONG", max=MAX_INSTALLMENTS)
        parts = [(q2(row.principal_part), q2(row.interest_part)) for row in rows]
        total = sum((p for p, _ in parts), ZERO)
        if total != principal:
            raise EngineError(
                "CUSTOM_PRINCIPAL_MISMATCH", expected=str(principal), actual=str(total),
                difference=str(principal - total),
            )
        return parts
    interest_each = (
        q2(terms.custom_interest) if terms.custom_interest is not None else q2(principal * r)
    )
    if interest_each < 0:
        raise EngineError("SCHEDULE_ROW_NEGATIVE", seq=1)
    if terms.custom_principal is not None:
        return _fill_fixed_principal(principal, q2(terms.custom_principal), interest_each)
    n = installment_count(terms)
    return [(p, interest_each) for p in _equal_split(principal, n)]


def _simple_days(terms: LoanTerms) -> tuple[date, Decimal]:
    value = terms.term_value
    if value is None or value <= 0:
        raise EngineError("TERM_INVALID")
    if terms.term_unit is TermUnit.MONTHS:
        maturity = add_months(terms.disbursal_date, value)
        # A monthly rate over whole months counts 30 days a month, so 3 months at 2 % is 6 %.
        days = value * 30 if terms.rate_basis is RateBasis.MONTH else (maturity - terms.disbursal_date).days
    elif terms.term_unit is TermUnit.DAYS:
        maturity = terms.disbursal_date + timedelta(days=value)
        days = value
    else:
        raise EngineError("TERM_INVALID")
    day_count = 30 if terms.rate_basis is RateBasis.MONTH else 365
    interest = q2(terms.principal * terms.rate / Decimal(100) / day_count * days)
    return maturity, interest


def _monthly_equivalent(terms: LoanTerms, total_interest: Decimal, start: date, end: date) -> Decimal:
    """Rate in % per month to compare with the lender's maximum permitted rate.

    Reducing-balance and interest-only loans charge interest on what is still owed, so their
    nominal rate is the comparable figure. Flat-style loans charge on the original principal
    for the whole period, so the flat equivalent (total interest / principal / months) is used.
    """
    if terms.method in (Method.REDUCING, Method.INTEREST_ONLY, Method.SIMPLE_DAYS) or (
        terms.method is Method.FIXED_AMOUNT and terms.fixed_style is FixedStyle.REDUCING
    ):
        return q2(terms.rate if terms.rate_basis is RateBasis.MONTH else terms.rate / 12)
    months = Decimal(max((end - start).days, 1)) / 30
    return q2(total_interest / terms.principal / months * 100)


def build_schedule(terms: LoanTerms) -> ScheduleResult:
    _validate(terms)
    with localcontext() as ctx:
        ctx.prec = 40
        r = periodic_rate(terms.rate, terms.rate_basis, terms.frequency)
        first_due = terms.first_due_date or one_period_after(terms.disbursal_date, terms.frequency)

        if terms.method is Method.SIMPLE_DAYS:
            maturity, interest = _simple_days(terms)
            rows = _make_rows(terms.principal, [maturity], [(terms.principal, interest)])
            first_due = maturity
        else:
            if terms.method is Method.REDUCING:
                parts = _reducing_parts(terms.principal, r, installment_count(terms))
            elif terms.method is Method.FLAT:
                parts = _flat_parts(terms.principal, r, installment_count(terms))
            elif terms.method is Method.INTEREST_ONLY:
                parts = _interest_only_parts(terms.principal, r, installment_count(terms))
            elif terms.method is Method.FIXED_AMOUNT:
                if terms.fixed_installment is None:
                    raise EngineError("INSTALLMENT_INVALID")
                parts = _fixed_amount_parts(terms.principal, r, terms.fixed_installment, terms.fixed_style)
            else:
                parts = _custom_parts(terms, r)
            rows = _make_rows(terms.principal, due_dates(first_due, len(parts), terms.frequency), parts)

        total_interest = sum((row.interest_part for row in rows), ZERO)
        total_principal = sum((row.principal_part for row in rows), ZERO)
        maturity_date = rows[-1].due_date
        return ScheduleResult(
            rows=rows,
            installment=rows[0].installment,
            last_installment=rows[-1].installment,
            total_principal=total_principal,
            total_interest=total_interest,
            total_payable=total_principal + total_interest,
            installments=len(rows),
            first_due_date=first_due,
            maturity_date=maturity_date,
            periodic_rate=r,
            monthly_rate_equivalent=_monthly_equivalent(
                terms, total_interest, terms.disbursal_date, maturity_date
            ),
        )
