"""Engine options for vehicle and land loans: rounded EMI, advance EMIs, odd first period,
decimal rates and the true cost (APR-style rate including charges)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine import BrokenPeriod, EngineError, LoanTerms, build_schedule, true_cost
from app.engine.dates import add_months
from app.engine.types import FixedStyle, Frequency, Method, RateBasis, TermUnit

GIVEN = date(2026, 1, 5)


def terms(**kw: object) -> LoanTerms:
    base: dict[str, object] = dict(
        principal=D("100000"), rate=D("2"), rate_basis=RateBasis.MONTH, term_value=12,
        term_unit=TermUnit.MONTHS, frequency=Frequency.MONTHLY, method=Method.REDUCING,
        disbursal_date=GIVEN,
    )
    base.update(kw)
    return LoanTerms(**base)  # type: ignore[arg-type]


def cost(t: LoanTerms, received: D | None = None) -> D:
    s = build_schedule(t)
    c = true_cost(t.disbursal_date, received or t.principal, [(r.due_date, r.installment) for r in s.rows], t.frequency)
    assert c is not None
    return c.monthly_percent


# ------------------------------------------------------------------- decimal rates

def test_decimal_rate_like_2_45_percent_a_month() -> None:
    s = build_schedule(terms(rate=D("2.45")))
    r = D("0.0245")
    growth = (1 + r) ** 12
    assert s.installment == (D("100000") * r * growth / (growth - 1)).quantize(D("0.01"))
    assert s.installment == D("9719.22")
    assert sum(row.principal_part for row in s.rows) == D("100000")


@pytest.mark.parametrize("rate", [D("1.5"), D("2.45"), D("2.125"), D("0.75"), D("18.5")])
def test_decimal_rates_flat_and_interest_only(rate: D) -> None:
    flat = build_schedule(terms(method=Method.FLAT, rate=rate))
    assert flat.total_interest == (D("100000") * rate / 100 * 12).quantize(D("0.01"))
    io = build_schedule(terms(method=Method.INTEREST_ONLY, rate=rate))
    assert io.rows[0].interest_part == (D("100000") * rate / 100).quantize(D("0.01"))


# ------------------------------------------------------------------- rounded EMI

def test_emi_rounded_up_to_10_last_is_smaller() -> None:
    plain = build_schedule(terms())
    s = build_schedule(terms(emi_rounding=D("10")))
    assert s.unrounded_installment == plain.installment == D("9455.96")
    assert s.installment == D("9460.00")
    assert all(row.installment == D("9460.00") for row in s.rows[:-1])
    assert s.last_installment < s.installment
    assert sum(row.principal_part for row in s.rows) == D("100000")
    assert s.total_interest <= plain.total_interest  # paying a little more each month never costs more


@pytest.mark.parametrize("step", [D("1"), D("10"), D("100")])
def test_rounding_steps_reducing_and_flat(step: D) -> None:
    for method in (Method.REDUCING, Method.FLAT):
        s = build_schedule(terms(method=method, emi_rounding=step, principal=D("73450")))
        assert s.installment % step == 0
        assert sum(row.principal_part for row in s.rows) == D("73450")
        assert s.installments <= 12


def test_flat_rounding_keeps_interest_per_installment() -> None:
    s = build_schedule(terms(method=Method.FLAT, rate=D("12"), rate_basis=RateBasis.YEAR, term_value=36, emi_rounding=D("10")))
    assert s.unrounded_installment == D("3777.78") and s.installment == D("3780.00")
    assert {row.interest_part for row in s.rows} == {D("1000.00")}
    assert s.total_interest == D("36000.00")
    assert s.last_installment == D("3700.00")


def test_rounding_ignored_for_methods_that_set_their_own_amounts() -> None:
    io = build_schedule(terms(method=Method.INTEREST_ONLY, emi_rounding=D("10")))
    assert io.installment == D("2000.00")


def test_rounding_must_be_a_known_step() -> None:
    with pytest.raises(EngineError) as e:
        build_schedule(terms(emi_rounding=D("7")))
    assert e.value.code == "ROUNDING_INVALID"


# ------------------------------------------------------------------- advance EMIs

def test_one_advance_emi_is_due_today_with_no_interest() -> None:
    s = build_schedule(terms(advance_installments=1))
    first, second = s.rows[0], s.rows[1]
    assert first.due_date == GIVEN and first.interest_part == 0 and first.principal_part == s.installment
    assert second.due_date == add_months(GIVEN, 1)
    assert s.installments == 12 and s.advance_amount == s.installment == D("9270.55")
    assert s.maturity_date == add_months(GIVEN, 11)
    assert sum(row.principal_part for row in s.rows) == D("100000")
    assert s.installment < build_schedule(terms()).installment


def test_advance_emis_on_a_flat_loan_charge_flat_interest_on_every_installment() -> None:
    s = build_schedule(terms(method=Method.FLAT, advance_installments=2))
    assert [row.due_date for row in s.rows[:3]] == [GIVEN, GIVEN, add_months(GIVEN, 1)]
    assert s.total_interest == D("24000.00") and s.advance_amount == 2 * s.installment


def test_advance_with_rounding() -> None:
    s = build_schedule(terms(advance_installments=1, emi_rounding=D("100")))
    assert s.installment == D("9300.00") and s.advance_amount == D("9300.00")
    assert sum(row.principal_part for row in s.rows) == D("100000")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"advance_installments": 1, "method": Method.INTEREST_ONLY}, "ADVANCE_NOT_FOR_METHOD"),
        ({"advance_installments": 12}, "ADVANCE_TOO_MANY"),
        ({"advance_installments": 13}, "ADVANCE_INVALID"),
        ({"advance_installments": -1}, "ADVANCE_INVALID"),
    ],
)
def test_advance_rules(change: dict[str, object], code: str) -> None:
    with pytest.raises(EngineError) as e:
        build_schedule(terms(**change))
    assert e.value.code == code


# ------------------------------------------------------------------- odd first period

def test_first_period_10_days_longer_adds_10_days_interest_to_the_first_installment() -> None:
    s = build_schedule(terms(first_due_date=date(2026, 2, 15), broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert s.broken_period_days == 10
    assert s.broken_period_interest == D("666.67")  # 1,00,000 x 2 % / 30 x 10
    assert s.first_installment == D("9455.96") + D("666.67")
    assert s.installment == D("9455.96")
    assert [row.due_date.day for row in s.rows] == [15] * 12


def test_first_period_11_days_shorter_takes_11_days_off() -> None:
    s = build_schedule(terms(first_due_date=date(2026, 1, 25), broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert s.broken_period_days == -11 and s.broken_period_interest == D("-733.33")
    assert s.rows[0].interest_part == D("2000.00") - D("733.33")


def test_extra_days_collected_up_front() -> None:
    s = build_schedule(terms(first_due_date=date(2026, 2, 15), broken_period=BrokenPeriod.UPFRONT))
    assert s.broken_period_upfront == D("666.67") and s.broken_period_interest == 0
    assert s.first_installment == D("9455.96")


def test_no_adjustment_when_the_first_due_date_is_one_period_away_or_switched_off() -> None:
    assert build_schedule(terms(broken_period=BrokenPeriod.FIRST_INSTALLMENT)).broken_period_interest == 0
    off = build_schedule(terms(first_due_date=date(2026, 2, 15)))
    assert off.broken_period_interest == 0 and off.first_installment == D("9455.96")


def test_month_end_disbursal_counts_the_short_month_as_a_full_month() -> None:
    s = build_schedule(terms(disbursal_date=date(2026, 1, 31), first_due_date=date(2026, 2, 28),
                             broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert s.broken_period_days == 0 and s.broken_period_interest == 0


def test_odd_period_on_flat_weekly_and_yearly_rates() -> None:
    flat = build_schedule(terms(method=Method.FLAT, first_due_date=date(2026, 2, 20),
                                broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert flat.broken_period_interest == D("1000.00")  # 15 days on the full principal
    weekly = build_schedule(terms(frequency=Frequency.WEEKLY, term_value=10, term_unit=TermUnit.INSTALLMENTS,
                                  first_due_date=date(2026, 1, 15), broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert weekly.broken_period_days == 3 and weekly.broken_period_interest == D("200.00")
    yearly = build_schedule(terms(rate=D("24"), rate_basis=RateBasis.YEAR, first_due_date=date(2026, 2, 15),
                                  broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert yearly.broken_period_interest == D("657.53")  # 1,00,000 x 24 % / 365 x 10


def test_odd_period_with_advance_charges_only_what_is_still_owed() -> None:
    s = build_schedule(terms(advance_installments=1, first_due_date=date(2026, 2, 15),
                             broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    owed = D("100000") - s.advance_amount
    assert s.broken_period_interest == (owed * D("0.02") / 30 * 10).quantize(D("0.01"))
    assert s.rows[1].due_date == date(2026, 2, 15)


def test_fixed_amount_first_installment_carries_the_odd_days() -> None:
    s = build_schedule(terms(method=Method.FIXED_AMOUNT, fixed_installment=D("5000"), fixed_style=FixedStyle.REDUCING,
                             first_due_date=date(2026, 2, 10), broken_period=BrokenPeriod.FIRST_INSTALLMENT))
    assert s.first_installment == D("5000") + s.broken_period_interest
    assert s.installment == D("5000.00")


# ------------------------------------------------------------------- true cost

def test_true_cost_of_a_plain_loan_is_its_rate_whatever_the_frequency() -> None:
    assert cost(terms()) == D("2.00")
    assert cost(terms(rate=D("2.45"))) == D("2.45")
    assert cost(terms(frequency=Frequency.WEEKLY, term_value=52, term_unit=TermUnit.INSTALLMENTS)) == D("2.00")
    assert cost(terms(frequency=Frequency.DAILY, term_value=100, term_unit=TermUnit.DAYS)) == D("2.00")
    assert cost(terms(disbursal_date=date(2026, 1, 31))) == D("2.00")
    assert cost(terms(advance_installments=2)) == D("2.00")


def test_true_cost_of_flat_and_charges() -> None:
    flat = terms(method=Method.FLAT, rate=D("12"), rate_basis=RateBasis.YEAR, term_value=36)
    assert cost(flat) == D("1.77")  # 12 % flat a year ~ 21.2 % a year reducing
    assert cost(terms(), received=D("98000")) > D("2.30")  # a 2 % fee taken out raises the cost
    assert cost(terms(rate=D("0"))) == D("0.00")


def test_true_cost_needs_money_received() -> None:
    assert true_cost(GIVEN, D("0"), [(GIVEN, D("1"))], Frequency.MONTHLY) is None


# ------------------------------------------------------------------- properties

@settings(max_examples=150, deadline=None)
@given(
    principal=st.decimals(min_value=D("5000"), max_value=D("5000000"), places=0),
    rate=st.decimals(min_value=D("0"), max_value=D("5"), places=2),
    n=st.integers(min_value=3, max_value=60),
    advance=st.integers(min_value=0, max_value=2),
    step=st.sampled_from([D("0.01"), D("1"), D("10"), D("100")]),
    shift=st.integers(min_value=-20, max_value=40),
    method=st.sampled_from([Method.REDUCING, Method.FLAT]),
    mode=st.sampled_from(list(BrokenPeriod)),
)
def test_options_never_break_the_schedule(
    principal: D, rate: D, n: int, advance: int, step: D, shift: int, method: Method, mode: BrokenPeriod
) -> None:
    first_due = add_months(GIVEN, 1)
    first_due = date.fromordinal(first_due.toordinal() + shift)
    if first_due <= GIVEN:
        return
    s = build_schedule(terms(principal=principal, rate=rate, term_value=n, advance_installments=advance,
                             emi_rounding=step, first_due_date=first_due, broken_period=mode, method=method))
    assert sum(row.principal_part for row in s.rows) == principal
    assert all(row.principal_part >= 0 and row.interest_part >= 0 and row.installment > 0 for row in s.rows)
    assert s.installments <= n
    assert [row.due_date for row in s.rows[:advance]] == [GIVEN] * advance
    assert all(row.due_date > GIVEN for row in s.rows[advance:])
    if step > D("0.01"):
        assert s.installment % step == 0
