"""Document attachments (PRD section 8).

Files are checked by content (magic bytes), not by extension, scanned for malware, stored under a
random name in a private folder that is never served directly, and opened only through short-lived
signed links issued after a permission check. Every view or download is audit-logged.
"""

from __future__ import annotations

import io
import os
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.config import get_settings
from app.core.errors import AppError
from app.deps import Ctx
from app.models import Borrower, Document, Loan
from app.security import crypto, tokens
from app.security.tokens import now
from app.services import audit, scanner

BORROWER_TYPES = {"aadhaar", "pan", "photo", "address_proof", "other"}
LOAN_TYPES = {"agreement", "promissory_note", "cheque", "photo", "other"}
OWNER_ONLY_TYPES = {"aadhaar", "pan"}  # Staff see only that the file exists


def sniff(data: bytes) -> str | None:
    """Real file type from content. Anything else (an .exe renamed .pdf) is rejected."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) > 12 and data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"}:
        return "image/heic"
    return None


def _heic_to_jpeg(data: bytes) -> bytes:
    try:
        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        with Image.open(io.BytesIO(data)) as img:
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=88)
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - any decoder failure means an unusable file
        raise AppError("FILE_UNREADABLE", 422) from exc


def _owner(ctx: Ctx, owner_type: str, owner_id: uuid.UUID) -> None:
    model = Borrower if owner_type == "borrower" else Loan
    row = ctx.db.get(model, owner_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise AppError("OWNER_NOT_FOUND", 404)


def storage_path(key: str) -> Path:
    return get_settings().storage_dir / key[:2] / key


def upload(ctx: Ctx, *, owner_type: str, owner_id: uuid.UUID, doc_type: str, note: str | None, filename: str,
           data: bytes) -> Document:
    allowed = BORROWER_TYPES if owner_type == "borrower" else LOAN_TYPES
    if owner_type not in ("borrower", "loan") or doc_type not in allowed:
        raise AppError("DOC_TYPE_INVALID", 422)
    _owner(ctx, owner_type, owner_id)
    limit = ctx.business.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise AppError("FILE_TOO_LARGE", 413, max_mb=ctx.business.max_upload_mb)
    if not data:
        raise AppError("FILE_EMPTY", 422)
    count = ctx.db.scalar(
        select(func.count()).select_from(Document)
        .where(Document.owner_type == owner_type, Document.owner_id == owner_id, Document.deleted_at.is_(None))
    ) or 0
    if count >= ctx.business.max_files_per_owner:
        raise AppError("TOO_MANY_FILES", 409, max=ctx.business.max_files_per_owner)
    mime = sniff(data)
    if mime is None:
        audit.from_ctx(ctx, "document.rejected", owner_type, owner_id, {"reason": "type", "name": filename[:100]})
        ctx.db.commit()
        raise AppError("FILE_TYPE_NOT_ALLOWED", 415)
    try:
        clean = scanner.is_clean(data)
    except scanner.ScannerUnavailable as exc:
        raise AppError("SCANNER_UNAVAILABLE", 503) from exc
    if not clean:
        audit.from_ctx(ctx, "document.rejected", owner_type, owner_id, {"reason": "malware", "name": filename[:100]})
        ctx.db.commit()
        raise AppError("FILE_INFECTED", 422)
    if mime == "image/heic":
        data, mime = _heic_to_jpeg(data), "image/jpeg"
        filename = os.path.splitext(filename)[0] + ".jpg"
    key = secrets.token_hex(24)
    path = storage_path(key)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".part")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    doc = Document(
        owner_type=owner_type, owner_id=owner_id, doc_type=doc_type, storage_key=key,
        original_name=os.path.basename(filename)[:255] or "file", mime=mime, size=len(data),
        sha256=crypto.sha256_hex(data), scan_status="clean", note=note, uploaded_by=ctx.user.id,
    )
    ctx.db.add(doc)
    ctx.db.flush()
    audit.from_ctx(ctx, "document.uploaded", "document", doc.id, {"owner_type": owner_type, "owner_id": str(owner_id),
                                                                  "doc_type": doc_type, "size": len(data)})
    ctx.db.commit()
    return doc


def visible_to(ctx: Ctx, doc: Document) -> bool:
    return ctx.is_owner or doc.doc_type not in OWNER_ONLY_TYPES


def serialize(ctx: Ctx, doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id, "owner_type": doc.owner_type, "owner_id": doc.owner_id, "doc_type": doc.doc_type,
        "original_name": doc.original_name, "mime": doc.mime, "size": doc.size, "note": doc.note,
        "created_at": doc.created_at, "can_view": visible_to(ctx, doc), "can_download": ctx.is_owner,
        "can_delete": ctx.is_owner,
    }


def list_for(ctx: Ctx, owner_type: str, owner_id: uuid.UUID) -> list[Document]:
    return list(ctx.db.scalars(
        select(Document).where(Document.owner_type == owner_type, Document.owner_id == owner_id,
                               Document.deleted_at.is_(None)).order_by(Document.created_at.desc())
    ))


def _get(ctx: Ctx, doc_id: uuid.UUID) -> Document:
    doc = ctx.db.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", 404)
    return doc


def link(ctx: Ctx, doc_id: uuid.UUID, download: bool) -> str:
    doc = _get(ctx, doc_id)
    if not visible_to(ctx, doc):
        raise AppError("OWNER_ONLY", 403)
    if download and not ctx.is_owner:
        raise AppError("OWNER_ONLY", 403)
    audit.from_ctx(ctx, "document.download" if download else "document.view", "document", doc.id,
                   {"doc_type": doc.doc_type})
    ctx.db.commit()
    return f"/api/v1/files/{tokens.file_link_token(doc.id, ctx.user.id, download)}"


def open_signed(db: Any, token: str) -> tuple[Document, bytes, bool]:
    claims = tokens.decode(token, "file", kind="file")
    if not claims:
        raise AppError("LINK_EXPIRED", 403)
    doc = db.get(Document, uuid.UUID(claims["doc"]))
    if doc is None or doc.deleted_at is not None or doc.scan_status != "clean":
        raise AppError("DOCUMENT_NOT_FOUND", 404)
    data = storage_path(doc.storage_key).read_bytes()
    if crypto.sha256_hex(data) != doc.sha256:
        raise AppError("FILE_CORRUPT", 500)
    return doc, data, bool(claims.get("dl"))


def soft_delete(ctx: Ctx, doc_id: uuid.UUID) -> None:
    doc = _get(ctx, doc_id)
    doc.deleted_at = now()
    doc.purge_after = now() + timedelta(days=30)
    audit.from_ctx(ctx, "document.deleted", "document", doc.id, {"doc_type": doc.doc_type})
    ctx.db.commit()


def purge_expired(db: Any) -> int:
    """Permanently remove files 30 days after a soft delete (nightly job)."""
    count = 0
    for doc in db.scalars(select(Document).where(Document.purge_after <= now(), Document.purged_at.is_(None))):
        path = storage_path(doc.storage_key)
        if path.exists():
            path.unlink()
        doc.purged_at = now()
        count += 1
    db.commit()
    return count
