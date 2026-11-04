"""Errors return a stable code; the app shows the message in the current language (PRD section 9).

Error responses never echo request values, so an Aadhaar number typed into a form can never
come back in an error body or a log line (PRD section 12, acceptance check 14).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.engine.errors import EngineError

log = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, code: str, status_code: int = 400, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.params = params


def not_found(entity: str = "ENTITY") -> AppError:
    return AppError(f"{entity}_NOT_FOUND", 404)


def forbidden(code: str = "FORBIDDEN") -> AppError:
    return AppError(code, 403)


def _body(code: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, **extra}}


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v if isinstance(v, (int, float, bool)) or v is None else str(v) for k, v in params.items()}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, params=_safe_params(exc.params)), status_code=exc.status_code)

    @app.exception_handler(EngineError)
    async def engine_error(_: Request, exc: EngineError) -> JSONResponse:
        return JSONResponse(_body(exc.code, params=_safe_params(exc.params)), status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", ()) if part != "body"]
            ctx = err.get("ctx") or {}
            code = ctx.get("code") if isinstance(ctx.get("code"), str) else None
            fields.append({"field": ".".join(loc), "code": code or str(err.get("type", "invalid")).upper()})
        return JSONResponse(_body("VALIDATION_FAILED", fields=fields), status_code=422)

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, __: StaleDataError) -> JSONResponse:
        return JSONResponse(_body("EDIT_CONFLICT"), status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        log.warning("integrity error", extra={"constraint": getattr(exc.orig, "diag", None) and exc.orig.diag.constraint_name})  # type: ignore[union-attr]
        return JSONResponse(_body("CONFLICT"), status_code=409)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "NOT_AUTHENTICATED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error: %s", type(exc).__name__, exc_info=exc)
        return JSONResponse(_body("INTERNAL_ERROR"), status_code=500)
