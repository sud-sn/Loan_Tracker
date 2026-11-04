"""Server-side English and Tamil text for PDFs and reminder messages (PRD section 9).

Strings live in ``app/i18n/{lang}.json``; adding a language means adding a file. Money uses Indian
grouping in both languages (₹1,00,000.00); digits stay Western; dates are DD/MM/YYYY.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

I18N_DIR = Path(__file__).resolve().parent.parent / "i18n"
LANGS = ("en", "ta")


@lru_cache
def catalog(lang: str) -> dict[str, str]:
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        path = I18N_DIR / "en.json"
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


def t(lang: str, key: str, **params: Any) -> str:
    text = catalog(lang).get(key) or catalog("en").get(key) or key
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def group_indian(integer: int) -> str:
    s = str(abs(integer))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts) + "," + tail
    return ("-" if integer < 0 else "") + out


def money(value: Decimal | int | None, symbol: bool = True) -> str:
    if value is None:
        return ""
    d = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    return f"{sign}{'₹' if symbol else ''}{group_indian(int(whole))}.{frac}"


def fmt_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def long_date(lang: str, value: date | None) -> str:
    if not value:
        return ""
    month = t(lang, f"month.{value.month}")
    return f"{value.day:02d} {month} {value.year}"


def name(lang: str, name_en: str | None, name_ta: str | None) -> str:
    """Show the name in the current language, falling back to the other (PRD section 9)."""
    first, second = (name_ta, name_en) if lang == "ta" else (name_en, name_ta)
    return first or second or ""


# ----------------------------------------------------------------- amounts in words

_EN_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
            "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _en_below_1000(n: int) -> str:
    words = []
    if n >= 100:
        words.append(f"{_EN_ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        words.append(_EN_TENS[n // 10] + (f"-{_EN_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_EN_ONES[n])
    return " ".join(words)


def _en_words(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    for div, label in ((10**7, "crore"), (10**5, "lakh"), (1000, "thousand")):
        if n >= div:
            parts.append(f"{_en_words(n // div) if div == 10**7 else _en_below_1000(n // div)} {label}")
            n %= div
    if n:
        parts.append(_en_below_1000(n))
    return " ".join(parts)


_TA_ONES = ["", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"]
_TA_TEENS = ["பத்து", "பதினொன்று", "பன்னிரண்டு", "பதின்மூன்று", "பதினான்கு", "பதினைந்து", "பதினாறு", "பதினேழு",
             "பதினெட்டு", "பத்தொன்பது"]
_TA_TENS = ["", "", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது", "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"]
_TA_TENS_JOIN = ["", "", "இருபத்து", "முப்பத்து", "நாற்பத்து", "ஐம்பத்து", "அறுபத்து", "எழுபத்து", "எண்பத்து",
                 "தொண்ணூற்று"]
_TA_HUNDREDS = ["", "நூறு", "இருநூறு", "முந்நூறு", "நானூறு", "ஐந்நூறு", "அறுநூறு", "எழுநூறு", "எண்ணூறு",
                "தொள்ளாயிரம்"]
_TA_HUNDREDS_JOIN = ["", "நூற்று", "இருநூற்று", "முந்நூற்று", "நானூற்று", "ஐந்நூற்று", "அறுநூற்று", "எழுநூற்று",
                     "எண்ணூற்று", "தொள்ளாயிரத்து"]


def _ta_below_100(n: int) -> str:
    if n < 10:
        return _TA_ONES[n]
    if n < 20:
        return _TA_TEENS[n - 10]
    tens, ones = divmod(n, 10)
    return _TA_TENS[tens] if not ones else f"{_TA_TENS_JOIN[tens]} {_TA_ONES[ones]}"


def _ta_below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _ta_below_100(rest)
    if not rest:
        return _TA_HUNDREDS[hundreds]
    return f"{_TA_HUNDREDS_JOIN[hundreds]} {_ta_below_100(rest)}"


def _ta_count(n: int) -> str:
    return "ஒரு" if n == 1 else _ta_words(n)


def _ta_words(n: int) -> str:
    if n == 0:
        return "பூஜ்ஜியம்"
    parts: list[str] = []
    for div, last, joined in ((10**7, "கோடி", "கோடியே"), (10**5, "லட்சம்", "லட்சத்து"), (1000, "ஆயிரம்", "ஆயிரத்து")):
        if n >= div:
            count, n = divmod(n, div)
            parts.append(f"{_ta_count(count)} {joined if n else last}")
    if n:
        parts.append(_ta_below_1000(n))
    return " ".join(parts)


def amount_in_words(lang: str, value: Decimal) -> str:
    d = Decimal(value).quantize(Decimal("0.01"))
    rupees, paise = int(d), int((d - int(d)) * 100)
    if lang == "ta":
        text = f"{_ta_count(rupees) if rupees == 1 else _ta_words(rupees)} ரூபாய்"
        if paise:
            text += f" {_ta_words(paise)} பைசா"
        return text
    text = f"{_en_words(rupees)} {'rupee' if rupees == 1 else 'rupees'}"
    if paise:
        text += f" and {_en_words(paise)} paise"
    return text[0].upper() + text[1:] + " only"
