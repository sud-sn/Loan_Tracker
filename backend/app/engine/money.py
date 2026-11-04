"""Exact money helpers. Rupees are ``Decimal`` in code and integer paise in the database."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value: Decimal) -> Decimal:
    """Round half-up to 2 decimals (PRD section 4)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_paise(value: Decimal) -> int:
    return int((q2(value) * 100).to_integral_value())


def from_paise(paise: int) -> Decimal:
    return (Decimal(paise) / 100).quantize(CENT)


def parse_amount(text: str | int | Decimal) -> Decimal:
    """Parse a rupee amount, rejecting more than 2 decimals."""
    value = Decimal(str(text).replace(",", "").strip())
    if value != value.quantize(CENT):
        raise ValueError("more than 2 decimals")
    return value.quantize(CENT)
