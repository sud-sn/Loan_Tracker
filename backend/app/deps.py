"""Request dependencies: database session, the signed-in user, roles and step-up checks.

Authorization is enforced here, on the server, for every endpoint (PRD section 12); the UI
hiding a button is never the only protection.
"""

from __future__ import annotations

import hmac
import ipaddress
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import request_id_var
from app.db import get_db
from app.models import BusinessSettings, User
from app.security import tokens

DB = Annotated[Session, Depends(get_db)]


@dataclass
class Ctx:
    db: Session
    user: User
    business: BusinessSettings
    ip: str | None
    user_agent: str | None
    request_id: str | None

    @property
    def is_owner(self) -> bool:
        return self.user.role == "owner"

    @property
    def lang(self) -> str:
        return self.user.language


def session_version(user: User) -> int:
    return int(user.password_changed_at.timestamp()) if user.password_changed_at else 0


def client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def load_business(db: Session) -> BusinessSettings:
    row = db.scalars(select(BusinessSettings).limit(1)).first()
    if row is None:
        row = BusinessSettings()
        db.add(row)
        db.flush()
    return row


def get_ctx(request: Request, db: DB) -> Ctx:
    raw = request.cookies.get(tokens.ACCESS_COOKIE)
    claims = tokens.decode(raw, "access") if raw else None
    if not claims:
        raise AppError("NOT_AUTHENTICATED", 401)
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active or claims.get("sv") != session_version(user):
        raise AppError("NOT_AUTHENTICATED", 401)
    business = load_business(db)
    if user.role == "staff" and not business.staff_enabled:
        raise AppError("STAFF_DISABLED", 403)
    return Ctx(
        db=db, user=user, business=business, ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:300], request_id=request_id_var.get(),
    )


CtxDep = Annotated[Ctx, Depends(get_ctx)]


def require_owner(ctx: CtxDep) -> Ctx:
    if not ctx.is_owner:
        raise AppError("OWNER_ONLY", 403)
    return ctx


OwnerCtx = Annotated[Ctx, Depends(require_owner)]


def require_step_up(request: Request, ctx: OwnerCtx) -> Ctx:
    raw = request.cookies.get(tokens.STEP_UP_COOKIE)
    claims = tokens.decode(raw, "stepup") if raw else None
    if not claims or claims.get("sub") != str(ctx.user.id):
        raise AppError("STEP_UP_REQUIRED", 403)
    return ctx


StepUpCtx = Annotated[Ctx, Depends(require_step_up)]


def can_create_loans(ctx: CtxDep) -> Ctx:
    if not ctx.is_owner and not ctx.business.staff_can_create_loans:
        raise AppError("FORBIDDEN", 403)
    return ctx


LoanCreatorCtx = Annotated[Ctx, Depends(can_create_loans)]

CSRF_EXEMPT = {"/api/v1/auth/login", "/api/v1/auth/setup"}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF token plus an Origin check on every state-changing API call."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if request.method in UNSAFE and path.startswith("/api/"):
            settings = get_settings()
            origin = request.headers.get("origin")
            if origin and settings.env == "production" and origin.rstrip("/") != settings.app_origin.rstrip("/"):
                return JSONResponse({"error": {"code": "BAD_ORIGIN"}}, status_code=403)
            if path not in CSRF_EXEMPT:
                cookie = request.cookies.get(tokens.CSRF_COOKIE, "")
                header = request.headers.get("x-csrf-token", "")
                if not cookie or not hmac.compare_digest(cookie, header):
                    return JSONResponse({"error": {"code": "CSRF_FAILED"}}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    CSP = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("Content-Security-Policy", self.CSP)
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        if get_settings().cookie_secure:
            h["Strict-Transport-Security"] = "max-age=31536000"
        return response
