"""Payment allocation (PRD section 5).

A payment goes to the oldest unpaid installment first; inside each installment it pays
penalty, then interest, then principal. Anything left moves to the next installment.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.engine.errors import EngineError
from app.engine.money import ZERO


@dataclass(frozen=True)
class OpenItem:
    item_id: str
    seq: int
    penalty_due: Decimal
    interest_due: Decimal
    principal_due: Decimal

    @property
    def total_due(self) -> Decimal:
        return self.penalty_due + self.interest_due + self.principal_due


@dataclass(frozen=True)
class AllocationLine:
    item_id: str
    seq: int
    penalty_part: Decimal
    interest_part: Decimal
    principal_part: Decimal

    @property
    def total(self) -> Decimal:
        return self.penalty_part + self.interest_part + self.principal_part


def allocate(amount: Decimal, items: list[OpenItem]) -> list[AllocationLine]:
    if amount <= 0:
        raise EngineError("AMOUNT_NOT_POSITIVE")
    outstanding = sum((item.total_due for item in items), ZERO)
    if amount > outstanding:
        raise EngineError("PAYMENT_EXCEEDS_OUTSTANDING", outstanding=str(outstanding))
    remaining = amount
    lines: list[AllocationLine] = []
    for item in sorted(items, key=lambda it: it.seq):
        if remaining <= 0:
            break
        if item.total_due <= 0:
            continue
        pen = min(remaining, max(item.penalty_due, ZERO))
        remaining -= pen
        intr = min(remaining, max(item.interest_due, ZERO))
        remaining -= intr
        prin = min(remaining, max(item.principal_due, ZERO))
        remaining -= prin
        if pen or intr or prin:
            lines.append(AllocationLine(item.item_id, item.seq, pen, intr, prin))
    return lines
