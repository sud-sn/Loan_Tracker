from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from app.core.errors import AppError
from app.deps import DB, CtxDep, OwnerCtx, StepUpCtx, client_ip, load_business
from app.models import User
from app.schemas.auth import (
    LanguageIn,
    LoginIn,
    MeOut,
    PasswordChangeIn,
    SetupIn,
    SetupStatusOut,
    StaffIn,
    StaffUpdateIn,
    StepUpIn,
    TotpCodeIn,
    TotpSetupOut,
    UserOut,
)
from app.schemas.common import Ok
from app.security import tokens
from app.services import audit
from app.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])
users = APIRouter(prefix="/users", tags=["users"])


def _me(db: DB, user: User, csrf: str | None) -> MeOut:
    b = load_business(db)
    return MeOut(user=UserOut.model_validate(user), csrf_token=csrf, staff_enabled=b.staff_enabled,
                 staff_can_create_loans=b.staff_can_create_loans)


@router.get("/setup", response_model=SetupStatusOut)
def setup_status(db: DB) -> SetupStatusOut:
    return SetupStatusOut(needs_setup=service.needs_setup(db))


@router.post("/setup", response_model=MeOut)
def setup(data: SetupIn, request: Request, response: Response, db: DB) -> MeOut:
    s = service.setup_owner(db, data.name, data.phone, data.password, data.language, client_ip(request),
                            request.headers.get("user-agent"))
    csrf = tokens.set_session_cookies(response, s.access, s.refresh)
    return _me(db, s.user, csrf)


@router.post("/login", response_model=MeOut)
def login(data: LoginIn, request: Request, response: Response, db: DB) -> MeOut:
    s = service.login(db, data.phone, data.password, data.totp, client_ip(request), request.headers.get("user-agent"))
    csrf = tokens.set_session_cookies(response, s.access, s.refresh)
    return _me(db, s.user, csrf)


@router.post("/refresh", response_model=MeOut)
def refresh(request: Request, response: Response, db: DB) -> MeOut:
    s = service.refresh(db, request.cookies.get(tokens.REFRESH_COOKIE), client_ip(request),
                        request.headers.get("user-agent"))
    csrf = tokens.set_session_cookies(response, s.access, s.refresh)
    return _me(db, s.user, csrf)


@router.post("/logout", response_model=Ok)
def logout(request: Request, response: Response, db: DB) -> Ok:
    service.logout(db, request.cookies.get(tokens.REFRESH_COOKIE))
    tokens.clear_session_cookies(response)
    return Ok()


@router.get("/me", response_model=MeOut)
def me(ctx: CtxDep) -> MeOut:
    return _me(ctx.db, ctx.user, None)


@router.post("/step-up", response_model=Ok)
def step_up(data: StepUpIn, response: Response, ctx: OwnerCtx) -> Ok:
    tokens.set_step_up_cookie(response, service.step_up(ctx, data.password, data.totp))
    return Ok()


@router.put("/password", response_model=Ok)
def change_password(data: PasswordChangeIn, response: Response, ctx: CtxDep) -> Ok:
    s = service.change_password(ctx, data.current_password, data.new_password)
    tokens.set_session_cookies(response, s.access, s.refresh)
    return Ok()


@router.put("/language", response_model=UserOut)
def set_language(data: LanguageIn, ctx: CtxDep) -> User:
    ctx.user.language = data.language
    audit.from_ctx(ctx, "user.language", "user", ctx.user.id, {"language": data.language})
    ctx.db.commit()
    return ctx.user


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(ctx: OwnerCtx) -> TotpSetupOut:
    secret, uri = service.totp_begin(ctx)
    return TotpSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/totp/enable", response_model=Ok)
def totp_enable(data: TotpCodeIn, ctx: OwnerCtx) -> Ok:
    service.totp_enable(ctx, data.code)
    return Ok()


@router.post("/totp/disable", response_model=Ok)
def totp_disable(ctx: StepUpCtx) -> Ok:
    service.totp_disable(ctx)
    return Ok()


@users.get("", response_model=list[UserOut])
def list_users(ctx: OwnerCtx) -> list[User]:
    from sqlalchemy import select

    return list(ctx.db.scalars(select(User).order_by(User.created_at)))


@users.post("", response_model=UserOut)
def create_staff(data: StaffIn, ctx: OwnerCtx) -> User:
    return service.create_staff(ctx, data.name, data.phone, data.password, data.language)


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, data: StaffUpdateIn, request: Request, ctx: OwnerCtx) -> User:
    claims = tokens.decode(request.cookies.get(tokens.STEP_UP_COOKIE, ""), "stepup")
    stepped_up = bool(claims and claims.get("sub") == str(ctx.user.id))
    if data.role is not None and not stepped_up:
        raise AppError("STEP_UP_REQUIRED", 403)
    return service.update_user(ctx, user_id, name=data.name, is_active=data.is_active, role=data.role,
                               new_password=data.new_password, stepped_up=stepped_up)
