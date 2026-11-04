"""Text helpers: NFC normalisation, phone and Aadhaar parsing, and a phonetic search key.

The search key lets "Murugan", "murukan" and "முருகன்" find the same person: Tamil is
romanised, then both scripts are folded to a rough phonetic form (g→k, d→t, long vowels short,
double letters single). It is only a search aid; names are always shown as typed.
"""

from __future__ import annotations

import re
import unicodedata

from app.security.verhoeff import is_valid_aadhaar


def nfc(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    return cleaned or None


def normalize_phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("PHONE_INVALID")
    return digits


def normalize_aadhaar(value: str) -> str:
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"\d{12}", digits):
        raise ValueError("AADHAAR_FORMAT")
    if not is_valid_aadhaar(digits):
        raise ValueError("AADHAAR_CHECKSUM")
    return digits


def mask_aadhaar(last4: str | None) -> str | None:
    return f"XXXX XXXX {last4}" if last4 else None


def has_tamil(value: str) -> bool:
    return any("஀" <= ch <= "௿" for ch in value)


_VOWELS = {
    "அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu", "எ": "e", "ஏ": "ee",
    "ஐ": "ai", "ஒ": "o", "ஓ": "oo", "ஔ": "au", "ஃ": "h",
}
_CONSONANTS = {
    "க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "t", "ண": "n", "த": "th", "ந": "n", "ப": "p",
    "ம": "m", "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "zh", "ள": "l", "ற": "r", "ன": "n",
    "ஜ": "j", "ஷ": "sh", "ஸ": "s", "ஹ": "h", "ஶ": "sh",
}
_SIGNS = {
    "ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu", "ெ": "e", "ே": "ee", "ை": "ai",
    "ொ": "o", "ோ": "oo", "ௌ": "au",
}
_VIRAMA = "்"


def tamil_to_latin(value: str) -> str:
    out: list[str] = []
    chars = list(unicodedata.normalize("NFC", value))
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _CONSONANTS:
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == _VIRAMA:
                out.append(_CONSONANTS[ch])
                i += 2
                continue
            if nxt in _SIGNS:
                out.append(_CONSONANTS[ch] + _SIGNS[nxt])
                i += 2
                continue
            out.append(_CONSONANTS[ch] + "a")
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _SIGNS or ch == _VIRAMA:
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_FOLDS = [
    ("sh", "s"), ("ch", "s"), ("zh", "l"), ("th", "t"), ("dh", "t"), ("ph", "p"), ("bh", "p"),
    ("kh", "k"), ("gh", "k"), ("ee", "i"), ("oo", "u"), ("aa", "a"), ("ii", "i"), ("uu", "u"),
    ("w", "v"), ("g", "k"), ("d", "t"), ("b", "p"), ("j", "s"), ("c", "k"), ("q", "k"), ("z", "s"),
    ("x", "ks"), ("f", "p"),
]


def phonetic_key(value: str | None) -> str:
    if not value:
        return ""
    text = tamil_to_latin(value) if has_tamil(value) else value
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if ch.isascii() and (ch.isalnum() or ch == " "))
    for src, dst in _FOLDS:
        text = text.replace(src, dst)
    text = re.sub(r"(.)\1+", r"\1", text)  # double letters
    text = re.sub(r"h", "", text)  # breathy h is rarely written consistently
    return re.sub(r"\s+", " ", text).strip()


def search_key(name_en: str | None, name_ta: str | None) -> str:
    return " ".join(part for part in (phonetic_key(name_en), phonetic_key(name_ta)) if part)
