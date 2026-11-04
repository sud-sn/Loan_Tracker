"""Accounts and sessions (PRD sections 2 and 12)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pyotp
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import limiter
from app.core.text import normalize_phone
from app.deps import Ctx, session_version
from app.models import RefreshToken, User
from app.security import crypto, passwords, tokens
from app.services import audit

_DUMMY_HASH = passwords.hash_password("dummy-password-for-timing")


@dataclass
class Session_:
    user: User
    access: str
    refresh: str


def _phone(value: str) -> str:
    try:
        phone = normalize_phone(value)
    except ValueError as exc:
        raise AppError("PHONE_INVALID", 422) from exc
    if phone is None:
        raise AppError("PHONE_INVALID", 422)
    return phone


def _check_policy(password: str, phone: str) -> None:
    problem = passwords.policy_error(password, phone)
    if problem:
        raise AppError(problem, 422)


def needs_setup(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) == 0


def _issue(db: Session, user: User, ip: str | None, ua: str | None, family: uuid.UUID | None = None) -> Session_:
    raw, digest = tokens.new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id, token_hash=digest, family_id=family or uuid.uuid4(),
            expires_at=tokens.now() + timedelta(days=get_settings().refresh_token_days),
            user_agent=ua, ip=ip,
        )
    )
    return Session_(user, tokens.access_token(user.id, user.role, session_version(user)), raw)


def setup_owner(db: Session, name: str, phone: str, password: str, language: str, ip: str | None,
                ua: str | None) -> Session_:
    """The first account created is the Owner (PRD section 2)."""
    limiter.check(f"setup:{ip}", 5)
    db.execute(text('LOCK TABLE "user" IN EXCLUSIVE MODE'))
    if not needs_setup(db):
        raise AppError("SETUP_DONE", 409)
    phone = _phone(phone)
    _check_policy(password, phone)
    user = User(name=name, phone=phone, password_hash=passwords.hash_password(password), role="owner",
                language=language, password_changed_at=tokens.now())
    db.add(user)
    db.flush()
    audit.record(db, "auth.setup_owner", user_id=user.id, entity_type="user", entity_id=user.id, ip=ip,
                 user_agent=ua)
    session = _issue(db, user, ip, ua)
    db.commit()
    return session


def _verify_totp(db: Session, user: User, code: str | None) -> bool:
    if not user.totp_enabled or not user.totp_secret_encrypted:
        return True
    if not code:
        return False
    totp = pyotp.TOTP(crypto.decrypt(user.totp_secret_encrypted, crypto.TOTP))
    now_step = int(tokens.now().timestamp()) // 30
    for offset in (-1, 0, 1):  # allow one step of clock drift
        step = now_step + offset
        if totp.at(step * 30) == code.strip() and (user.totp_last_step or 0) < step:
            user.totp_last_step = step  # reject replays of the same code
            return True
    return False


def _fail(db: Session, user: User, ip: str | None, ua: str | None, reason: str) -> None:
    user.failed_attempts += 1
    threshold = get_settings().lockout_threshold
    if user.failed_attempts >= threshold:
        minutes = min(2 ** (user.failed_attempts - threshold), 60)
        user.locked_until = tokens.now() + timedelta(minutes=minutes)
    audit.record(db, "auth.login_failed", user_id=user.id, entity_type="user", entity_id=user.id,
                 changes={"reason": reason, "attempts": user.failed_attempts}, ip=ip, user_agent=ua)
    db.commit()


def login(db: Session, phone: str, password: str, totp_code: str | None, ip: str | None, ua: str | None) -> Session_:
    limiter.check(f"login-ip:{ip}", get_settings().login_rate_per_minute)
    try:
        phone = _phone(phone)
    except AppError:
        raise AppError("INVALID_CREDENTIALS", 401) from None
    limiter.check(f"login-phone:{phone}", get_settings().login_rate_per_minute)
    user = db.scalars(select(User).where(User.phone == phone).with_for_update()).first()
    if user is None or not user.is_active:
        passwords.verify_password(_DUMMY_HASH, password)  # same timing as a real check
        raise AppError("INVALID_CREDENTIALS", 401)
    if user.locked_until and user.locked_until > tokens.now():
        retry = int((user.locked_until - tokens.now()).total_seconds()) + 1
        raise AppError("ACCOUNT_LOCKED", 423, retry_after=retry)
    if not passwords.verify_password(user.password_hash, password):
        _fail(db, user, ip, ua, "password")
        raise AppError("INVALID_CREDENTIALS", 401)
    if user.totp_enabled and not totp_code:
        db.rollback()
        raise AppError("TOTP_REQUIRED", 401)
    if not _verify_totp(db, user, totp_code):
        _fail(db, user, ip, ua, "totp")
        raise AppError("TOTP_INVALID", 401)
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = tokens.now()
    audit.record(db, "auth.login", user_id=user.id, entity_type="user", entity_id=user.id, ip=ip, user_agent=ua)
    session = _issue(db, user, ip, ua)
    db.commit()
    return session


def refresh(db: Session, raw: str | None, ip: str | None, ua: str | None) -> Session_:
    if not raw:
        raise AppError("NOT_AUTHENTICATED", 401)
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == tokens.hash_token(raw)).with_for_update()
    ).first()
    if row is None:
        raise AppError("NOT_AUTHENTICATED", 401)
    if row.revoked_at is not None:
        # A rotated token was used again: someone may have copied it. End the whole family.
        db.execute(
            update(RefreshToken).where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=tokens.now())
        )
        audit.record(db, "auth.refresh_reuse", user_id=row.user_id, entity_type="user", entity_id=row.user_id,
                     ip=ip, user_agent=ua)
        db.commit()
        raise AppError("NOT_AUTHENTICATED", 401)
    user = db.get(User, row.user_id)
    if row.expires_at < tokens.now() or user is None or not user.is_active:
        raise AppError("NOT_AUTHENTICATED", 401)
    row.revoked_at = tokens.now()
    session = _issue(db, user, ip, ua, family=row.family_id)
    db.commit()
    return session


def logout(db: Session, raw: str | None) -> None:
    if raw:
        db.execute(
            update(RefreshToken).where(RefreshToken.token_hash == tokens.hash_token(raw)).values(revoked_at=tokens.now())
        )
        db.commit()


def step_up(ctx: Ctx, password: str, totp_code: str | None) -> str:
    limiter.check(f"stepup:{ctx.user.id}", 10)
    if not passwords.verify_password(ctx.user.password_hash, password) or not _verify_totp(ctx.db, ctx.user, totp_code):
        audit.from_ctx(ctx, "auth.step_up_failed", "user", ctx.user.id)
        ctx.db.commit()
        raise AppError("STEP_UP_FAILED", 401)
    audit.from_ctx(ctx, "auth.step_up", "user", ctx.user.id)
    ctx.db.commit()
    return tokens.step_up_token(ctx.user.id)


def change_password(ctx: Ctx, current: str, new: str) -> Session_:
    if not passwords.verify_password(ctx.user.password_hash, current):
        raise AppError("PASSWORD_WRONG", 401)
    _check_policy(new, ctx.user.phone)
    ctx.user.password_hash = passwords.hash_password(new)
    ctx.user.password_changed_at = tokens.now()
    ctx.db.execute(
        update(RefreshToken).where(RefreshToken.user_id == ctx.user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=tokens.now())
    )
    audit.from_ctx(ctx, "auth.password_changed", "user", ctx.user.id)
    session = _issue(ctx.db, ctx.user, ctx.ip, ctx.user_agent)
    ctx.db.commit()
    return session


def totp_begin(ctx: Ctx) -> tuple[str, str]:
    secret = pyotp.random_base32()
    ctx.user.totp_secret_encrypted = crypto.encrypt(secret, crypto.TOTP)
    ctx.user.totp_enabled = False
    ctx.db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=ctx.user.phone, issuer_name="Loan Tracker")
    return secret, uri


def totp_enable(ctx: Ctx, code: str) -> None:
    if not ctx.user.totp_secret_encrypted:
        raise AppError("TOTP_NOT_STARTED", 409)
    ctx.user.totp_enabled = True
    if not _verify_totp(ctx.db, ctx.user, code):
        ctx.db.rollback()
        raise AppError("TOTP_INVALID", 422)
    audit.from_ctx(ctx, "auth.totp_enabled", "user", ctx.user.id)
    ctx.db.commit()


def totp_disable(ctx: Ctx) -> None:
    ctx.user.totp_enabled = False
    ctx.user.totp_secret_encrypted = None
    audit.from_ctx(ctx, "auth.totp_disabled", "user", ctx.user.id)
    ctx.db.commit()


def create_staff(ctx: Ctx, name: str, phone: str, password: str, language: str) -> User:
    phone = _phone(phone)
    if ctx.db.scalars(select(User).where(User.phone == phone)).first():
        raise AppError("PHONE_IN_USE", 409)
    _check_policy(password, phone)
    user = User(name=name, phone=phone, password_hash=passwords.hash_password(password), role="staff",
                language=language, password_changed_at=tokens.now())
    ctx.db.add(user)
    ctx.db.flush()
    audit.from_ctx(ctx, "user.created", "user", user.id, {"role": "staff", "name": name})
    ctx.db.commit()
    return user


def update_user(ctx: Ctx, user_id: uuid.UUID, *, name: str | None, is_active: bool | None, role: str | None,
                new_password: str | None, stepped_up: bool) -> User:
    user = ctx.db.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", 404)
    changes: dict[str, object] = {}
    if role is not None and role != user.role:
        if not stepped_up:
            raise AppError("STEP_UP_REQUIRED", 403)
        if user.id == ctx.user.id:
            raise AppError("CANNOT_CHANGE_OWN_ROLE", 409)
        changes["role"] = [user.role, role]
        user.role = role
    if is_active is not None and is_active != user.is_active:
        if user.id == ctx.user.id:
            raise AppError("CANNOT_DEACTIVATE_SELF", 409)
        changes["is_active"] = [user.is_active, is_active]
        user.is_active = is_active
    if name:
        changes["name"] = [user.name, name]
        user.name = name
    if new_password:
        _check_policy(new_password, user.phone)
        user.password_hash = passwords.hash_password(new_password)
        user.password_changed_at = tokens.now()
        changes["password"] = "reset"  # noqa: S105 - an audit label, not a secret
    audit.from_ctx(ctx, "user.updated", "user", user.id, changes)
    ctx.db.commit()
    return user
