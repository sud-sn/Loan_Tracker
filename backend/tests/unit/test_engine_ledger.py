"""Allocation, penalty, status and settlement tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.engine.allocation import OpenItem, allocate
from app.engine.errors import EngineError
from app.engine.penalty import PaidEvent, PenaltyItem, PenaltyMode, PenaltyRule, accrued_penalty
from app.engine.settlement import SettlementItem, settlement
from app.engine.status import ItemState, ItemStatus, LoanStatus, ageing_bucket, item_status, summarize

TODAY = date(2026, 11, 4)


def test_allocation_oldest_first_penalty_interest_principal() -> None:
    items = [
        OpenItem("b", 2, D("0"), D("1850.88"), D("7605.08")),
        OpenItem("a", 1, D("50"), D("2000"), D("7455.96")),
    ]
    lines = allocate(D("10000"), items)
    assert lines[0].item_id == "a"
    assert (lines[0].penalty_part, lines[0].interest_part, lines[0].principal_part) == (
        D("50"), D("2000"), D("7455.96"),
    )
    assert lines[1].item_id == "b"
    assert (lines[1].penalty_part, lines[1].interest_part, lines[1].principal_part) == (
        D("0"), D("494.04"), D("0"),
    )
    assert sum(ln.total for ln in lines) == D("10000")


def test_partial_payment_pays_interest_before_principal() -> None:
    lines = allocate(D("2500"), [OpenItem("a", 1, D("0"), D("2000"), D("7455.96"))])
    assert (lines[0].interest_part, lines[0].principal_part) == (D("2000"), D("500"))


def test_overpayment_rejected() -> None:
    with pytest.raises(EngineError) as err:
        allocate(D("100.01"), [OpenItem("a", 1, D("0"), D("0"), D("100"))])
    assert err.value.code == "PAYMENT_EXCEEDS_OUTSTANDING"


def test_penalty_pct_month_accrues_daily_on_unpaid() -> None:
    due = TODAY - timedelta(days=10)
    items = [PenaltyItem("a", due, D("9000"))]
    rule = PenaltyRule(PenaltyMode.PCT_MONTH, D("3"))
    got = accrued_penalty(items, [], rule, TODAY)
    assert got["a"] == D("90.00")  # 9,000 x 3% / 30 x 10 days
    # Half paid six days after due. The payment counts from the next day:
    # 6 days on 9,000 (₹54) + 4 days on 4,500 (₹18).
    paid = [PaidEvent("a", due + timedelta(days=6), D("4500"))]
    assert accrued_penalty(items, paid, rule, TODAY)["a"] == D("72.00")


def test_penalty_per_day_is_per_loan_not_per_installment() -> None:
    items = [
        PenaltyItem("a", TODAY - timedelta(days=10), D("1000")),
        PenaltyItem("b", TODAY - timedelta(days=3), D("1000")),
    ]
    got = accrued_penalty(items, [], PenaltyRule(PenaltyMode.PER_DAY, D("20")), TODAY)
    assert got["a"] + got["b"] == D("200.00")


def test_penalty_off_and_grace_days() -> None:
    items = [PenaltyItem("a", TODAY - timedelta(days=10), D("1000"))]
    assert accrued_penalty(items, [], PenaltyRule(PenaltyMode.OFF, D("0")), TODAY)["a"] == 0
    got = accrued_penalty(items, [], PenaltyRule(PenaltyMode.PER_DAY, D("10"), grace_days=3), TODAY)
    assert got["a"] == D("70.00")


def state(seq: int, due: date, p: str, i: str, pen: str = "0", paid: bool = False) -> ItemState:
    return ItemState(str(seq), seq, due, D(p), D(i), D(pen), paid)


def test_item_statuses() -> None:
    assert item_status(state(1, TODAY - timedelta(days=1), "10", "0"), TODAY) is ItemStatus.OVERDUE
    assert item_status(state(1, TODAY, "10", "0"), TODAY) is ItemStatus.DUE_TODAY
    assert item_status(state(1, TODAY + timedelta(days=4), "10", "0"), TODAY) is ItemStatus.UPCOMING
    assert item_status(state(1, TODAY + timedelta(days=4), "10", "0", paid=True), TODAY) is ItemStatus.PARTIALLY_PAID
    assert item_status(state(1, TODAY - timedelta(days=4), "10", "0", paid=True), TODAY) is ItemStatus.OVERDUE
    assert item_status(state(1, TODAY - timedelta(days=4), "0", "0", paid=True), TODAY) is ItemStatus.PAID


def test_loan_summary_overdue_days_from_oldest_unpaid() -> None:
    items = [
        state(1, TODAY - timedelta(days=40), "0", "0", paid=True),
        state(2, TODAY - timedelta(days=10), "500", "100", paid=True),
        state(3, TODAY + timedelta(days=20), "600", "100"),
    ]
    s = summarize(items, TODAY, TODAY - timedelta(days=70), TODAY - timedelta(days=12), "active")
    assert s.status is LoanStatus.OVERDUE
    assert s.overdue_days == 10
    assert s.overdue_amount == D("600")
    assert s.days_since_last_payment == 12
    assert s.next_due_date == TODAY + timedelta(days=20)
    assert s.total_outstanding == D("1300")


def test_loan_due_soon_and_days_since_disbursal() -> None:
    items = [state(1, TODAY + timedelta(days=2), "500", "100")]
    s = summarize(items, TODAY, TODAY - timedelta(days=31), None, "active")
    assert s.status is LoanStatus.DUE_SOON
    assert s.days_since_last_payment == 31
    assert summarize(items, TODAY, TODAY, None, "closed").status is LoanStatus.CLOSED


@pytest.mark.parametrize(("days", "bucket"), [(0, "current"), (1, "1_7"), (7, "1_7"), (8, "8_30"),
                                              (31, "31_60"), (61, "61_90"), (91, "over_90")])
def test_ageing_buckets(days: int, bucket: str) -> None:
    assert ageing_bucket(days) == bucket


def sitem(seq: int, start: date, due: date, p: str, i: str, pp: str = "0", ip: str = "0") -> SettlementItem:
    return SettlementItem(str(seq), seq, start, due, D(p), D(i), D(pp), D(ip), D("0"))


def test_settlement_waives_future_interest_and_prorates_current() -> None:
    d0 = date(2026, 1, 1)
    items = [
        sitem(1, d0, date(2026, 1, 31), "8000", "2000", "8000", "2000"),
        sitem(2, date(2026, 1, 31), date(2026, 3, 2), "8000", "2000"),  # 30-day period
        sitem(3, date(2026, 3, 2), date(2026, 4, 1), "84000", "2000"),
    ]
    s = settlement(items, date(2026, 2, 15))  # 15 of 30 days into period 2
    assert s.principal == D("92000")
    assert s.interest == D("1000.00")
    assert s.interest_waived == D("3000.00")
    assert s.total == D("93000.00")


def test_settlement_credits_interest_paid_in_advance() -> None:
    d0 = date(2026, 1, 1)
    items = [
        sitem(1, d0, date(2026, 1, 31), "1000", "100", "1000", "100"),
        sitem(2, date(2026, 1, 31), date(2026, 3, 2), "1000", "100", "0", "100"),
        sitem(3, date(2026, 3, 2), date(2026, 4, 1), "1000", "100", "0", "100"),
    ]
    s = settlement(items, date(2026, 2, 15))
    assert s.credit == D("100")  # row 3's interest was paid early and is not earned yet
    assert s.principal == D("1900")
    assert s.lines[2].principal_waived == D("100")
    assert s.total == D("1900")
