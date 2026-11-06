"""Early-closure settlement figure (PRD section 5, decision ADR-0004).

Settlement on a date = all unpaid principal
                     + unpaid interest of installments already due
                     + interest of the current period, pro-rata to the days elapsed
                     + unpaid penalty
                     - interest already paid in advance on later installments (credited).

Interest of later periods is waived. This treats every method the same way, including flat
and fixed-amount loans, whose unearned future interest is not charged. The credit is booked
as a principal waiver on the last rows, so the ledger stays append-only.

Phase 2 adds two other ways to work out the interest of installments not yet due, which the
owner chooses when closing early (mostly for flat loans):

* ``RULE_OF_78``: the borrower gets back total interest x k(k+1) / n(n+1), where n is the number
  of installments and k those after the current period (the period running on the closing day is
  earned in full, as usual for this rule); the rest of their interest is charged;
* ``NONE``: no rebate; all their interest is charged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from app.engine.money import ZERO, q2


class Rebate(StrEnum):
    PRO_RATA = "pro_rata"  # interest to the day for the current period, later interest waived
    RULE_OF_78 = "rule_of_78"
    NONE = "none"


@dataclass(frozen=True)
class SettlementItem:
    item_id: str
    seq: int
    period_start: date  # previous due date, or the disbursal date for the first row
    due_date: date
    principal_part: Decimal
    interest_part: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    penalty_due: Decimal  # unpaid
    waived_interest: Decimal = ZERO
    waived_principal: Decimal = ZERO


@dataclass(frozen=True)
class SettlementLine:
    item_id: str
    seq: int
    penalty: Decimal
    interest: Decimal  # interest to collect on this row
    principal: Decimal  # principal to collect on this row
    interest_waived: Decimal
    principal_waived: Decimal


@dataclass(frozen=True)
class Settlement:
    on: date
    principal: Decimal
    interest: Decimal
    penalty: Decimal
    credit: Decimal
    total: Decimal
    interest_waived: Decimal
    lines: tuple[SettlementLine, ...]


def settlement(items: list[SettlementItem], on: date, rebate: Rebate = Rebate.PRO_RATA) -> Settlement:
    rows: list[list[Decimal]] = []  # [penalty, i_take, i_waive, p_unpaid]
    ordered = sorted(items, key=lambda x: x.seq)
    credit = ZERO
    current_found = False
    # Interest that may still be charged on installments not yet due (Rule of 78 / no rebate).
    future = [it for it in ordered if it.due_date > on]
    keep_left = ZERO
    if rebate is Rebate.NONE:
        keep_left = sum((it.interest_part for it in future), ZERO)
    elif rebate is Rebate.RULE_OF_78:
        n, k = len(ordered), max(len(future) - 1, 0)
        total = sum((it.interest_part for it in ordered), ZERO)
        back = q2(total * k * (k + 1) / (n * (n + 1))) if n else ZERO
        keep_left = max(sum((it.interest_part for it in future), ZERO) - back, ZERO)
    with localcontext() as ctx:
        ctx.prec = 40
        for it in ordered:
            p_unpaid = max(it.principal_part - it.principal_paid - it.waived_principal, ZERO)
            i_unpaid = max(it.interest_part - it.interest_paid - it.waived_interest, ZERO)
            if it.due_date <= on:
                i_take, i_waive = i_unpaid, ZERO
            elif rebate is not Rebate.PRO_RATA:
                allowed = min(keep_left, it.interest_part)
                keep_left -= allowed
                i_take = min(max(allowed - it.interest_paid - it.waived_interest, ZERO), i_unpaid)
                i_waive = i_unpaid - i_take
                credit += max(it.interest_paid - allowed, ZERO)
            elif not current_found:
                current_found = True
                span = max((it.due_date - it.period_start).days, 1)
                elapsed = min(max((on - it.period_start).days, 0), span)
                earned = q2(it.interest_part * Decimal(elapsed) / Decimal(span))
                i_take = min(max(earned - it.interest_paid - it.waived_interest, ZERO), i_unpaid)
                i_waive = i_unpaid - i_take
            else:
                i_take, i_waive = ZERO, i_unpaid
                credit += it.interest_paid
            rows.append([max(it.penalty_due, ZERO), i_take, i_waive, p_unpaid])

    total_principal = sum((r[3] for r in rows), ZERO)
    credit = min(credit, total_principal)
    # Apply the credit from the last row backwards.
    p_waive = [ZERO] * len(rows)
    left = credit
    for idx in range(len(rows) - 1, -1, -1):
        if left <= 0:
            break
        take = min(left, rows[idx][3])
        p_waive[idx] = take
        left -= take

    lines = tuple(
        SettlementLine(it.item_id, it.seq, r[0], r[1], r[3] - p_waive[k], r[2], p_waive[k])
        for k, (it, r) in enumerate(zip(ordered, rows, strict=True))
    )
    principal = sum((ln.principal for ln in lines), ZERO)
    interest = sum((ln.interest for ln in lines), ZERO)
    penalty = sum((ln.penalty for ln in lines), ZERO)
    waived = sum((ln.interest_waived for ln in lines), ZERO)
    return Settlement(on, principal, interest, penalty, credit, principal + interest + penalty, waived, lines)
