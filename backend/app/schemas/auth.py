from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Lang, Schema


class SetupIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=16)
    password: str = Field(min_length=1, max_length=256)
    language: Lang = "en"


class LoginIn(Schema):
    phone: str = Field(min_length=10, max_length=16)
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=10)


class StepUpIn(Schema):
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=10)


class PasswordChangeIn(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class LanguageIn(Schema):
    language: Lang


class TotpCodeIn(Schema):
    code: str = Field(min_length=6, max_length=10)


class TotpSetupOut(Schema):
    secret: str
    otpauth_uri: str


class UserOut(Schema):
    id: uuid.UUID
    name: str
    phone: str
    role: Literal["owner", "staff"]
    language: Lang
    totp_enabled: bool
    is_active: bool
    last_login: datetime | None


class MeOut(Schema):
    user: UserOut
    csrf_token: str | None = None
    staff_enabled: bool
    staff_can_create_loans: bool


class SetupStatusOut(Schema):
    needs_setup: bool


class StaffIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=16)
    password: str = Field(min_length=1, max_length=256)
    language: Lang = "en"


class StaffUpdateIn(Schema):
    name: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    role: Literal["owner", "staff"] | None = None
    new_password: str | None = Field(default=None, max_length=256)
