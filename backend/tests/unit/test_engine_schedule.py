"""Interest engine tests. The section-4 fixtures of the PRD are the source of truth."""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal as D

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.engine import EngineError, LoanTerms, build_schedule
from app.engine.dates import add_months, due_dates
from app.engine.types import CustomRow, FixedStyle, Frequency, Method, RateBasis, TermUnit

DISBURSED = date(2026, 1, 5)


def terms(**kw: object) -> LoanTerms:
    base: dict[str, object] = dict(
        principal=D("100000"), rate=D("2"), rate_basis=RateBasis.MONTH, term_value=12,
        term_unit=TermUnit.MONTHS, frequency=Frequency.MONTHLY, method=Method.REDUCING,
        disbursal_date=DISBURSED,
    )
    base.update(kw)
    return LoanTerms(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------- PRD section 4 fixtures


def test_reducing_balance_fixture_matches_prd_to_the_paisa() -> None:
    s = build_schedule(terms())
    assert s.installment == D("9455.96")
    assert s.last_installment == D("9455.97")
    assert s.total_interest == D("13471.53")
    assert s.total_payable == D("113471.53")
    assert s.total_principal == D("100000.00")
    expected = {
        1: ("9455.96", "7455.96", "2000.00", "92544.04"),
        2: ("9455.96", "7605.08", "1850.88", "84938.96"),
        3: ("9455.96", "7757.18", "1698.78", "77181.78"),
        11: ("9455.96", "9088.77", "367.19", "9270.56"),
        12: ("9455.97", "9270.56", "185.41", "0.00"),
    }
    for row in s.rows:
        if row.seq in expected:
            inst, p, i, bal = expected[row.seq]
            assert (row.installment, row.principal_part, row.interest_part, row.closing_balance) == (
                D(inst), D(p), D(i), D(bal),
            ), row.seq


def test_flat_fixture() -> None:
    s = build_schedule(terms(method=Method.FLAT))
    assert s.total_interest == D("24000.00")
    for row in s.rows[:-1]:
        assert (row.installment, row.principal_part, row.interest_part) == (
            D("10333.33"), D("8333.33"), D("2000.00"),
        )
    # The last installment absorbs rounding: 11 x 8,333.33 = 91,666.63, so 8,333.37 is left.
    assert s.rows[-1].principal_part == D("8333.37")
    assert s.rows[-1].installment == D("10333.37")
    assert s.total_principal == D("100000.00")


def test_interest_only_fixture() -> None:
    s = build_schedule(terms(method=Method.INTEREST_ONLY))
    assert all(r.installment == D("2000.00") and r.principal_part == 0 for r in s.rows[:-1])
    assert s.rows[-1].principal_part == D("100000.00")
    assert s.rows[-1].installment == D("102000.00")


def test_simple_interest_90_days_fixture() -> None:
    s = build_schedule(
        terms(method=Method.SIMPLE_DAYS, frequency=Frequency.SINGLE, term_value=90, term_unit=TermUnit.DAYS)
    )
    assert len(s.rows) == 1
    assert s.total_interest == D("6000.00")
    assert s.rows[0].installment == D("106000.00")
    assert s.maturity_date == date(2026, 4, 5)


def test_simple_interest_yearly_rate_uses_365_days() -> None:
    s = build_schedule(
        terms(method=Method.SIMPLE_DAYS, frequency=Frequency.SINGLE, term_value=73, term_unit=TermUnit.DAYS,
              rate=D("24"), rate_basis=RateBasis.YEAR)
    )
    assert s.total_interest == D("4800.00")  # 1,00,000 x 24% / 365 x 73


# ---------------------------------------------------------------- fixed amount every installment


def test_fixed_amount_flat_borrower_pays_set_amount_and_app_finds_the_period() -> None:
    # Borrower wants to pay ₹10,000 a month: ₹2,000 interest + ₹8,000 principal.
    s = build_schedule(terms(method=Method.FIXED_AMOUNT, fixed_installment=D("10000"), term_value=None))
    assert s.installments == 13  # 12 x 8,000 = 96,000, so 4,000 is left for month 13
    assert all(r.installment == D("10000.00") for r in s.rows[:-1])
    assert all(r.interest_part == D("2000.00") for r in s.rows)
    assert s.rows[-1].principal_part == D("4000.00")
    assert s.rows[-1].installment == D("6000.00")
    assert s.total_principal == D("100000.00")


def test_fixed_amount_reducing_style() -> None:
    s = build_schedule(
        terms(method=Method.FIXED_AMOUNT, fixed_installment=D("10000"), fixed_style=FixedStyle.REDUCING)
    )
    assert s.rows[0].interest_part == D("2000.00")
    assert s.rows[1].interest_part == D("1840.00")  # 2% of 92,000
    assert all(r.installment == D("10000.00") for r in s.rows[:-1])
    assert s.rows[-1].installment <= D("10000.00")
    assert s.rows[-1].closing_balance == 0
    assert s.installments == 12
    assert s.total_principal == D("100000.00")


def test_fixed_amount_equal_to_emi_reproduces_emi_schedule() -> None:
    emi = build_schedule(terms())
    fixed = build_schedule(
        terms(method=Method.FIXED_AMOUNT, fixed_installment=D("9455.96"), fixed_style=FixedStyle.REDUCING)
    )
    assert [r.interest_part for r in fixed.rows] == [r.interest_part for r in emi.rows]
    assert fixed.installments == 12


def test_fixed_amount_too_small_to_cover_interest_is_rejected() -> None:
    with pytest.raises(EngineError) as err:
        build_schedule(terms(method=Method.FIXED_AMOUNT, fixed_installment=D("2000")))
    assert err.value.code == "INSTALLMENT_TOO_SMALL"
    with pytest.raises(EngineError) as err:
        build_schedule(
            terms(method=Method.FIXED_AMOUNT, fixed_installment=D("1999.99"), fixed_style=FixedStyle.REDUCING)
        )
    assert err.value.code == "INSTALLMENT_TOO_SMALL"


def test_fixed_amount_daily_collection() -> None:
    # ₹10,000 at 3% a month, collected ₹110 a day (flat interest ₹10/day, ₹100 principal).
    s = build_schedule(
        terms(principal=D("10000"), rate=D("3"), frequency=Frequency.DAILY, method=Method.FIXED_AMOUNT,
              fixed_installment=D("110"))
    )
    assert s.installments == 100
    assert s.rows[0].interest_part == D("10.00")
    assert s.rows[1].due_date == date(2026, 1, 7)


# ---------------------------------------------------------------- custom split (lender sets the amounts)


def test_custom_fill_same_split_each_month() -> None:
    s = build_schedule(
        terms(method=Method.CUSTOM, custom_principal=D("8000"), custom_interest=D("1500"), term_value=None)
    )
    assert s.installments == 13
    assert all(r.interest_part == D("1500.00") for r in s.rows)
    assert s.rows[-1].principal_part == D("4000.00")
    assert s.total_principal == D("100000.00")


def test_custom_term_only_divides_principal_and_uses_rate_for_interest() -> None:
    s = build_schedule(terms(method=Method.CUSTOM))
    flat = build_schedule(terms(method=Method.FLAT))
    assert [r.installment for r in s.rows] == [r.installment for r in flat.rows]


def test_custom_explicit_rows() -> None:
    rows = (CustomRow(D("30000"), D("2000")), CustomRow(D("30000"), D("1400")), CustomRow(D("40000"), D("800")))
    s = build_schedule(terms(method=Method.CUSTOM, custom_rows=rows))
    assert [r.installment for r in s.rows] == [D("32000.00"), D("31400.00"), D("40800.00")]
    assert [r.closing_balance for r in s.rows] == [D("70000.00"), D("40000.00"), D("0.00")]


def test_custom_rows_must_add_up_to_principal() -> None:
    rows = (CustomRow(D("30000"), D("2000")), CustomRow(D("30000"), D("1400")))
    with pytest.raises(EngineError) as err:
        build_schedule(terms(method=Method.CUSTOM, custom_rows=rows))
    assert err.value.code == "CUSTOM_PRINCIPAL_MISMATCH"
    assert err.value.params["difference"] == "40000.00"


# ---------------------------------------------------------------- dates and validation


def test_due_day_31_clamps_to_short_months_and_comes_back() -> None:
    dates = due_dates(date(2026, 1, 31), 4, Frequency.MONTHLY)
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert add_months(date(2027, 12, 31), 2) == date(2028, 2, 29)


def test_first_due_defaults_to_one_period_after_disbursal() -> None:
    assert build_schedule(terms()).rows[0].due_date == date(2026, 2, 5)
    weekly = build_schedule(terms(frequency=Frequency.WEEKLY, term_value=12, term_unit=TermUnit.INSTALLMENTS))
    assert weekly.rows[0].due_date == date(2026, 1, 12)


def test_weekly_rate_conversion_from_monthly_rate() -> None:
    s = build_schedule(
        terms(frequency=Frequency.WEEKLY, method=Method.FLAT, term_value=3, term_unit=TermUnit.MONTHS)
    )
    assert s.installments == 13  # 90 days / 7, rounded up
    assert s.rows[0].interest_part == D("466.67")  # 1,00,000 x 2% x 7/30


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"principal": D("0")}, "PRINCIPAL_INVALID"),
        ({"principal": D("10.005")}, "AMOUNT_TOO_MANY_DECIMALS"),
        ({"rate": D("-1")}, "RATE_INVALID"),
        ({"term_value": 0}, "TERM_INVALID"),
        ({"frequency": Frequency.SINGLE}, "FREQUENCY_METHOD_MISMATCH"),
        ({"method": Method.SIMPLE_DAYS}, "FREQUENCY_METHOD_MISMATCH"),
        ({"first_due_date": DISBURSED}, "FIRST_DUE_NOT_AFTER_DISBURSAL"),
        ({"term_value": 5000, "frequency": Frequency.DAILY, "term_unit": TermUnit.DAYS}, "TERM_TOO_LONG"),
    ],
)
def test_invalid_terms_return_codes(change: dict[str, object], code: str) -> None:
    with pytest.raises(EngineError) as err:
        build_schedule(terms(**change))
    assert err.value.code == code


def test_zero_rate_reducing() -> None:
    s = build_schedule(terms(rate=D("0"), term_value=3))
    assert [r.principal_part for r in s.rows] == [D("33333.33"), D("33333.33"), D("33333.34")]
    assert s.total_interest == 0


def test_monthly_rate_equivalent_for_rate_warning() -> None:
    assert build_schedule(terms()).monthly_rate_equivalent == D("2.00")
    assert build_schedule(terms(rate=D("24"), rate_basis=RateBasis.YEAR)).monthly_rate_equivalent == D("2.00")
    custom = build_schedule(terms(method=Method.CUSTOM, custom_principal=D("10000"), custom_interest=D("3000")))
    assert custom.monthly_rate_equivalent > D("2.9")


def test_schedule_generation_360_installments_under_100ms() -> None:
    start = time.perf_counter()
    for _ in range(5):
        build_schedule(terms(term_value=360))
    assert (time.perf_counter() - start) / 5 < 0.1


# ---------------------------------------------------------------- property tests

money = st.decimals(min_value=D("100"), max_value=D("50000000"), places=2, allow_nan=False, allow_infinity=False)
rates = st.decimals(min_value=D("0"), max_value=D("10"), places=2, allow_nan=False, allow_infinity=False)
methods = st.sampled_from([Method.REDUCING, Method.FLAT, Method.INTEREST_ONLY, Method.CUSTOM])
freqs = st.sampled_from([Frequency.MONTHLY, Frequency.WEEKLY, Frequency.DAILY])


@settings(max_examples=300, deadline=None)
@given(principal=money, rate=rates, n=st.integers(min_value=1, max_value=120), method=methods, freq=freqs)
def test_principal_repaid_equals_principal_lent(
    principal: D, rate: D, n: int, method: Method, freq: Frequency
) -> None:
    assume(not (method is Method.INTEREST_ONLY and rate == 0))
    try:
        s = build_schedule(
            terms(principal=principal, rate=rate, term_value=n, term_unit=TermUnit.INSTALLMENTS, method=method,
                  frequency=freq)
        )
    except EngineError as err:
        # Interest-only rows whose interest rounds to ₹0.00 are refused, never silently saved.
        assert err.code == "SCHEDULE_ROW_EMPTY" and method is Method.INTEREST_ONLY
        return
    assert s.total_principal == principal
    assert s.rows[-1].closing_balance == 0
    balance = principal
    for row in s.rows:
        assert row.installment == row.principal_part + row.interest_part
        assert row.principal_part >= 0 and row.interest_part >= 0
        balance -= row.principal_part
        assert row.closing_balance == balance
    # A reducing loan may finish a month early when rounding the installment up repays a tiny
    # principal before the last month (for example ₹100 over 104 months); it never runs longer.
    assert len(s.rows) == n or (method is Method.REDUCING and len(s.rows) < n)
    assert [r.due_date for r in s.rows] == sorted(r.due_date for r in s.rows)


@settings(max_examples=200, deadline=None)
@given(principal=money, rate=rates, extra=st.decimals(min_value=D("1"), max_value=D("100000"), places=2),
       style=st.sampled_from([FixedStyle.FLAT, FixedStyle.REDUCING]))
def test_fixed_amount_never_exceeds_the_agreed_amount(principal: D, rate: D, extra: D, style: FixedStyle) -> None:
    interest = (principal * rate / 100).quantize(D("0.01"))
    amount = interest + max(extra, (principal / 3000).quantize(D("0.01")) + D("0.01"))
    s = build_schedule(terms(principal=principal, rate=rate, method=Method.FIXED_AMOUNT,
                             fixed_installment=amount, fixed_style=style))
    assert s.total_principal == principal
    assert all(r.installment == amount for r in s.rows[:-1])
    assert s.rows[-1].installment < amount + 1  # a leftover under ₹1 is folded into the last row
