"""Phase 2 engine: new installments after a part-prepayment, and the rebate choices when a loan
is closed early."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine import EngineError, LoanTerms, build_schedule
from app.engine.reschedule import RescheduleMode, Style, reschedule
from app.engine.settlement import Rebate, SettlementItem, settlement
from app.engine.types import Frequency, Method, RateBasis, TermUnit

GIVEN = date(2026, 1, 5)


def loan(method: Method = Method.REDUCING, principal: str = "100000") -> object:
    return build_schedule(LoanTerms(
        principal=D(principal), rate=D("2"), rate_basis=RateBasis.MONTH, term_value=12, term_unit=TermUnit.MONTHS,
        frequency=Frequency.MONTHLY, method=method, disbursal_date=GIVEN))


def after_three(method: Method, extra: str, mode: RescheduleMode, paid_on: date | None = None) -> object:
    s = loan(method)
    rows = s.rows  # type: ignore[attr-defined]
    owed = rows[2].closing_balance - D(extra)
    return reschedule(balance=owed, rate=D("0.02"), style=Style(method.value), mode=mode,
                      dates=[r.due_date for r in rows[3:]], old_installment=s.installment,  # type: ignore[attr-defined]
                      old_first_interest=rows[3].interest_part, period_start=rows[2].due_date,
                      paid_on=paid_on or rows[2].due_date)


def test_reduce_emi_keeps_the_months_and_lowers_the_installment() -> None:
    r = after_three(Method.REDUCING, "20000", RescheduleMode.REDUCE_EMI)
    owed = loan().rows[2].closing_balance - D("20000")  # type: ignore[attr-defined]
    assert len(r.parts) == 9 and sum(p for p, _ in r.parts) == owed
    growth = D("1.02") ** 9
    assert r.installment == (owed * D("0.02") * growth / (growth - 1)).quantize(D("0.01"))
    assert r.installment < D("9455.96")


def test_reduce_term_keeps_the_installment_and_finishes_sooner() -> None:
    r = after_three(Method.REDUCING, "20000", RescheduleMode.REDUCE_TERM)
    assert r.installment == D("9455.96") and len(r.parts) < 9
    assert r.dates == tuple(d.due_date for d in loan().rows[3:3 + len(r.parts)])  # type: ignore[attr-defined]
    saved_by_emi = after_three(Method.REDUCING, "20000", RescheduleMode.REDUCE_EMI).total_interest
    assert r.total_interest < saved_by_emi  # finishing sooner saves more interest


def test_flat_and_interest_only_reschedule() -> None:
    flat = after_three(Method.FLAT, "30000", RescheduleMode.REDUCE_EMI)
    owed = D("100000") - 3 * D("8333.33") - D("30000")
    assert {i for _, i in flat.parts} == {(owed * D("0.02")).quantize(D("0.01"))}
    io = after_three(Method.INTEREST_ONLY, "40000", RescheduleMode.REDUCE_EMI)
    assert io.parts[0] == (D("0"), D("1200.00")) and io.parts[-1] == (D("60000"), D("1200.00"))
    with pytest.raises(EngineError) as e:
        after_three(Method.INTEREST_ONLY, "40000", RescheduleMode.REDUCE_TERM)
    assert e.value.code == "RESCHEDULE_MODE_NOT_FOR_METHOD"


def test_extra_paid_mid_period_splits_that_period_s_interest_by_days() -> None:
    s = loan()
    rows = s.rows  # type: ignore[attr-defined]
    start, due = rows[2].due_date, rows[3].due_date
    mid = start + timedelta(days=(due - start).days // 2)
    r = after_three(Method.REDUCING, "20000", RescheduleMode.REDUCE_EMI, paid_on=mid)
    new_full = ((rows[2].closing_balance - D("20000")) * D("0.02")).quantize(D("0.01"))
    assert new_full < r.parts[0][1] < rows[3].interest_part


def test_paying_everything_is_a_settlement_not_a_reschedule() -> None:
    with pytest.raises(EngineError) as e:
        reschedule(balance=D("0"), rate=D("0.02"), style=Style.REDUCING, mode=RescheduleMode.REDUCE_EMI,
                   dates=[GIVEN], old_installment=D("1"), old_first_interest=D("0"), period_start=GIVEN, paid_on=GIVEN)
    assert e.value.code == "PREPAY_USE_SETTLEMENT"


@settings(max_examples=120, deadline=None)
@given(extra_pct=st.integers(min_value=1, max_value=95), paid=st.integers(min_value=0, max_value=10),
       method=st.sampled_from([Method.REDUCING, Method.FLAT]), mode=st.sampled_from(list(RescheduleMode)))
def test_reschedule_always_repays_exactly_what_is_owed(extra_pct: int, paid: int, method: Method, mode: RescheduleMode) -> None:
    s = loan(method, "250000")
    rows = s.rows  # type: ignore[attr-defined]
    owed_before = rows[paid].closing_balance + rows[paid].principal_part if paid == 0 else rows[paid - 1].closing_balance
    extra = (owed_before * extra_pct / 100).quantize(D("0.01"))
    if extra >= owed_before:
        return
    start = GIVEN if paid == 0 else rows[paid - 1].due_date
    r = reschedule(balance=owed_before - extra, rate=D("0.02"), style=Style(method.value), mode=mode,
                   dates=[x.due_date for x in rows[paid:]], old_installment=s.installment,  # type: ignore[attr-defined]
                   old_first_interest=rows[paid].interest_part, period_start=start, paid_on=start)
    assert sum(p for p, _ in r.parts) == owed_before - extra
    assert all(p >= 0 and i >= 0 and p + i > 0 for p, i in r.parts)
    assert len(r.parts) <= 12 - paid


# ------------------------------------------------------------------- rebate choices

def flat_items(paid: int) -> list[SettlementItem]:
    s = loan(Method.FLAT)
    out, previous = [], GIVEN
    for r in s.rows:  # type: ignore[attr-defined]
        done = r.seq <= paid
        out.append(SettlementItem(str(r.seq), r.seq, previous, r.due_date, r.principal_part, r.interest_part,
                                  r.principal_part if done else D("0"), r.interest_part if done else D("0"), D("0")))
        previous = r.due_date
    return out


def test_rule_of_78_and_no_rebate_on_a_flat_loan() -> None:
    items = flat_items(3)
    on = items[2].due_date + timedelta(days=1)
    pro_rata = settlement(items, on)
    r78 = settlement(items, on, Rebate.RULE_OF_78)
    none = settlement(items, on, Rebate.NONE)
    # 24,000 flat interest; 9 of 12 left, the current one earned, so k = 8: back = 24,000 x 72 / 156.
    assert r78.interest == D("18000") - D("11076.92") == D("6923.08")
    assert none.interest == D("18000.00") and none.interest_waived == 0
    assert pro_rata.interest < r78.interest < none.interest
    assert pro_rata.principal == r78.principal == none.principal == D("100000") - 3 * D("8333.33")


def test_rebate_choices_credit_interest_paid_in_advance() -> None:
    items = flat_items(3)
    # Interest of installment 4 was paid in advance; with no rebate it is simply kept.
    items[3] = SettlementItem(items[3].item_id, 4, items[3].period_start, items[3].due_date, items[3].principal_part,
                              items[3].interest_part, D("0"), items[3].interest_part, D("0"))
    on = items[2].due_date + timedelta(days=1)
    none = settlement(items, on, Rebate.NONE)
    assert none.credit == 0 and none.interest == D("16000.00")
