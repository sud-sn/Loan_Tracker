"""Loan Tracker API. One version prefix, /api/v1; OpenAPI is generated from this code."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core import errors
from app.core.logging import RequestContextMiddleware, configure
from app.deps import CsrfMiddleware, SecurityHeadersMiddleware
from app.routers import admin, auth, borrowers, documents, home, loans


def create_app() -> FastAPI:
    settings = get_settings()
    configure(settings.log_level)
    app = FastAPI(
        title="Loan Tracker API",
        version="1.0.0",
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    errors.install(app)
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=[settings.app_origin], allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    for module in (auth, borrowers, loans, documents, home, admin):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(auth.users, prefix="/api/v1")
    app.include_router(admin.health)
    app.include_router(admin.health, prefix="/api")
    return app


app = create_app()
