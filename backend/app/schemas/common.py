from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Money crosses the API as a decimal string ("100000.00"), never as a float.
Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Lang = Literal["en", "ta"]
PaymentMode = Literal["cash", "upi", "bank", "cheque", "other"]
CashMode = Literal["cash", "upi", "bank", "other"]

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Ok(Schema):
    ok: bool = True


class DateRange(Schema):
    start: date
    end: date
