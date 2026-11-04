"""Password hashing and policy (PRD section 12): Argon2id, minimum 10 characters, breached check."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
MIN_LENGTH = 10

# Very common passwords of 10+ characters. A full offline breached list (for example the
# HIBP SHA-1 file) can be added with LT_BREACHED_PASSWORDS_FILE; nothing is sent online.
COMMON = {
    "1234567890", "0123456789", "0987654321", "1122334455", "1111111111", "0000000000", "9876543210",
    "qwertyuiop", "password12", "password123", "password1234", "iloveyou12", "1q2w3e4r5t", "qwerty1234",
    "qwerty12345", "abcdefghij", "abcd123456", "abc1234567", "abcdef1234", "asdfghjkl1", "zxcvbnm123",
    "1234qwerty", "123456789a", "a123456789", "1234567890a", "welcome123", "welcome@123", "admin12345",
    "administrator", "letmein123", "changeme123", "password@123", "Password@123", "passw0rd123",
    "india12345", "india@1234", "chennai123", "chennai@123", "tamilnadu1", "madurai123", "coimbatore",
    "sachin1234", "dhoni12345", "superstar1", "football12", "cricket123", "1qaz2wsx3edc", "qazwsxedc1",
    "computer12", "internet12", "monkey1234", "dragon1234", "sunshine12", "princess12", "baseball12",
    "starwars12", "whatever12", "trustno1234", "11223344556", "12341234123", "12121212121", "999999999999",
    "88888888888", "77777777777", "66666666666", "55555555555", "44444444444", "33333333333", "22222222222",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _breached_file() -> Path | None:
    return get_settings().breached_passwords_file


def _in_breached_file(password: str) -> bool:
    path = _breached_file()
    if path is None or not path.exists():
        return False
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    with path.open() as fh:
        for line in fh:
            if line[:40].upper() == digest:
                return True
    return False


def policy_error(password: str, phone: str | None = None) -> str | None:
    """Return an error code if the password is not acceptable, else ``None``."""
    if len(password) < MIN_LENGTH:
        return "PASSWORD_TOO_SHORT"
    if len(password) > 256:
        return "PASSWORD_TOO_LONG"
    lowered = password.lower()
    if lowered in {p.lower() for p in COMMON} or len(set(password)) <= 2:
        return "PASSWORD_TOO_COMMON"
    if phone and phone in password:
        return "PASSWORD_CONTAINS_PHONE"
    if _in_breached_file(password):
        return "PASSWORD_BREACHED"
    return None
