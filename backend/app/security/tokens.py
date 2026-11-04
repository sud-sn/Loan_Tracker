"""Session tokens, cookies, CSRF and signed file links (PRD section 12).

* ``lt_access``  short-lived JWT (HttpOnly, Secure, SameSite=Strict)
* ``lt_refresh`` opaque rotating refresh token (HttpOnly, path-limited to /api/v1/auth)
* ``lt_csrf``    double-submit token the app echoes in ``X-CSRF-Token``
* ``lt_stepup``  5-minute proof of a fresh password (and TOTP) for sensitive actions
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Response

from app.config import get_settings

ACCESS_COOKIE = "lt_access"
REFRESH_COOKIE = "lt_refresh"
CSRF_COOKIE = "lt_csrf"
STEP_UP_COOKIE = "lt_stepup"
ALGO = "HS256"


def _secret(kind: str) -> str:
    settings = get_settings()
    value = settings.file_link_secret if kind == "file" else settings.session_secret
    if len(value) < 32:
        raise RuntimeError(f"secret for {kind} tokens must be at least 32 characters")
    return value


def now() -> datetime:
    return datetime.now(UTC)


def encode(claims: dict[str, Any], minutes: float, kind: str = "session") -> str:
    issued = now()
    payload = {**claims, "iat": int(issued.timestamp()), "exp": int((issued + timedelta(minutes=minutes)).timestamp())}
    return jwt.encode(payload, _secret(kind), algorithm=ALGO)


def decode(token: str, typ: str, kind: str = "session") -> dict[str, Any] | None:
    try:
        claims: dict[str, Any] = jwt.decode(token, _secret(kind), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None


def access_token(user_id: uuid.UUID, role: str, session_version: int) -> str:
    return encode(
        {"sub": str(user_id), "role": role, "typ": "access", "sv": session_version},
        get_settings().access_token_minutes,
    )


def step_up_token(user_id: uuid.UUID) -> str:
    return encode({"sub": str(user_id), "typ": "stepup"}, get_settings().step_up_minutes)


def file_link_token(document_id: uuid.UUID, user_id: uuid.UUID, download: bool) -> str:
    seconds = get_settings().file_link_seconds
    return encode(
        {"doc": str(document_id), "sub": str(user_id), "typ": "file", "dl": download, "n": secrets.token_hex(4)},
        seconds / 60,
        kind="file",
    )


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _cookie(response: Response, name: str, value: str, max_age: int, *, http_only: bool = True, path: str = "/") -> None:
    response.set_cookie(
        name, value, max_age=max_age, path=path, httponly=http_only, secure=get_settings().cookie_secure,
        samesite="strict",
    )


def set_session_cookies(response: Response, access: str, refresh: str) -> str:
    settings = get_settings()
    csrf = secrets.token_urlsafe(24)
    _cookie(response, ACCESS_COOKIE, access, settings.access_token_minutes * 60, path="/api")
    _cookie(response, REFRESH_COOKIE, refresh, settings.refresh_token_days * 86400, path="/api/v1/auth")
    _cookie(response, CSRF_COOKIE, csrf, settings.refresh_token_days * 86400, http_only=False)
    return csrf


def set_step_up_cookie(response: Response, token: str) -> None:
    _cookie(response, STEP_UP_COOKIE, token, get_settings().step_up_minutes * 60, path="/api")


def clear_session_cookies(response: Response) -> None:
    for name, path in ((ACCESS_COOKIE, "/api"), (REFRESH_COOKIE, "/api/v1/auth"), (CSRF_COOKIE, "/"),
                       (STEP_UP_COOKIE, "/api")):
        response.delete_cookie(name, path=path, secure=get_settings().cookie_secure, samesite="strict")
