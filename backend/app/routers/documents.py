from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.errors import AppError
from app.deps import DB, CtxDep, OwnerCtx
from app.schemas.common import Ok
from app.services import documents as service

router = APIRouter(tags=["documents"])


class DocumentOut(BaseModel):
    id: uuid.UUID
    owner_type: Literal["borrower", "loan"]
    owner_id: uuid.UUID
    doc_type: str
    original_name: str
    mime: str
    size: int
    note: str | None
    created_at: Any
    can_view: bool
    can_download: bool
    can_delete: bool


class LinkOut(BaseModel):
    url: str
    expires_in: int


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(owner_type: Literal["borrower", "loan"], owner_id: uuid.UUID, ctx: CtxDep) -> list[dict[str, Any]]:
    return [service.serialize(ctx, d) for d in service.list_for(ctx, owner_type, owner_id)]


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    ctx: CtxDep,
    owner_type: Literal["borrower", "loan"] = Form(...),
    owner_id: uuid.UUID = Form(...),
    doc_type: str = Form(...),
    note: str | None = Form(default=None, max_length=500),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    limit = ctx.business.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError("FILE_TOO_LARGE", 413, max_mb=ctx.business.max_upload_mb)
    doc = service.upload(ctx, owner_type=owner_type, owner_id=owner_id, doc_type=doc_type, note=note,
                         filename=file.filename or "file", data=data)
    return service.serialize(ctx, doc)


@router.post("/documents/{doc_id}/link", response_model=LinkOut)
def document_link(doc_id: uuid.UUID, ctx: CtxDep, download: bool = False) -> LinkOut:
    from app.config import get_settings

    return LinkOut(url=service.link(ctx, doc_id, download), expires_in=get_settings().file_link_seconds)


@router.delete("/documents/{doc_id}", response_model=Ok)
def delete_document(doc_id: uuid.UUID, ctx: OwnerCtx) -> Ok:
    service.soft_delete(ctx, doc_id)
    return Ok()


@router.get("/files/{token}")
def serve_file(token: str, db: DB) -> Response:
    doc, data, download = service.open_signed(db, token)
    disposition = "attachment" if download else "inline"
    safe_name = "".join(ch for ch in doc.original_name if ch.isalnum() or ch in "._- ")[:80] or "file"
    return Response(
        data,
        media_type=doc.mime,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
