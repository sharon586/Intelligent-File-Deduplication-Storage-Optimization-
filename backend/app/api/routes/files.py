import logging
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi import File as FormFile
from fastapi import UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import client_ip, get_current_user, get_owned_file
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.db.session import get_db
from app.models import FileMetadata, StoredFile, User
from app.schemas.common import Page, make_page
from app.schemas.file import (
    DeletePreview,
    DeleteResponse,
    FileDetail,
    FileOut,
    GroupSummary,
    MetadataOut,
    ProtectRequest,
)
from app.services import storage
from app.services.audit import record_audit
from app.services.deletion import delete_files
from app.services.queue import enqueue_process_file
from app.services.validation import CATEGORIES, validate_upload

router = APIRouter(prefix="/files", tags=["Files"])
logger = logging.getLogger(__name__)

SORT_COLUMNS = {
    "uploaded_at": StoredFile.uploaded_at,
    "name": func.lower(StoredFile.original_filename),
    "size": StoredFile.size_bytes,
    "type": StoredFile.category,
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_detail(db: Session, record: StoredFile) -> FileDetail:
    data = FileOut.model_validate(record).model_dump()
    group = None
    if record.group is not None:
        original = next(
            (f for f in record.group.files if not f.is_duplicate),
            None,
        )
        group = GroupSummary(
            id=record.group.id,
            file_count=record.group.file_count,
            file_size=record.group.file_size,
            potential_savings=record.group.potential_savings,
            original_file_id=original.id if original else None,
            original_filename=original.original_filename if original else None,
        )
    meta = MetadataOut.model_validate(record.file_metadata) if record.file_metadata else None
    return FileDetail(**data, error_message=record.error_message, file_metadata=meta, group=group)


@router.post("/upload", response_model=FileOut, status_code=201)
def upload_file(
    request: Request,
    file: UploadFile = FormFile(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the upload to disk, then queue hashing/duplicate detection on the Celery worker."""
    first_chunk = file.file.read(settings.HASH_CHUNK_SIZE)
    if not first_chunk:
        raise ValidationAppError("Empty files are not allowed")
    info = validate_upload(file.filename or "", first_chunk[:2048])

    relative_path, size = storage.save_stream(first_chunk, file.file, user.id)
    try:
        record = StoredFile(
            owner_id=user.id,
            original_filename=info.filename,
            stored_path=relative_path,
            extension=info.extension,
            content_type=info.content_type,
            category=info.category,
            size_bytes=size,
            status="pending",
        )
        db.add(record)
        db.flush()
        db.add(
            FileMetadata(
                file_id=record.id,
                detected_mime=info.content_type,
                extension=info.extension,
                extra={"signature": info.detected_type, "client_content_type": file.content_type},
            )
        )
        record_audit(
            db,
            "file.upload",
            user_id=user.id,
            entity_type="file",
            entity_id=record.id,
            details={"filename": info.filename, "size_bytes": size},
            ip_address=client_ip(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.remove_file(relative_path)
        raise

    enqueue_process_file(record.id)
    db.refresh(record)
    return record


@router.get("", response_model=Page[FileOut])
def list_files(
    q: str | None = Query(None, max_length=255, description="Filename search"),
    file_type: str | None = Query(None, description=f"One of: {', '.join(CATEGORIES)}"),
    min_size: int | None = Query(None, ge=0, description="Minimum size in bytes"),
    max_size: int | None = Query(None, ge=0, description="Maximum size in bytes"),
    duplicate_status: Literal["any", "duplicate", "original", "unique"] = Query(
        "any",
        description="duplicate = redundant copies, original = originals that have copies, unique = no copies",
    ),
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: Literal["uploaded_at", "name", "size", "type"] = "uploaded_at",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file_type is not None and file_type not in CATEGORIES:
        raise ValidationAppError(f"file_type must be one of: {', '.join(CATEGORIES)}")
    if min_size is not None and max_size is not None and min_size > max_size:
        raise ValidationAppError("min_size cannot be greater than max_size")
    if date_from and date_to and date_from > date_to:
        raise ValidationAppError("date_from cannot be after date_to")

    conditions = [StoredFile.owner_id == user.id]
    if q:
        conditions.append(StoredFile.original_filename.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    if file_type:
        conditions.append(StoredFile.category == file_type)
    if min_size is not None:
        conditions.append(StoredFile.size_bytes >= min_size)
    if max_size is not None:
        conditions.append(StoredFile.size_bytes <= max_size)
    if date_from:
        conditions.append(StoredFile.uploaded_at >= datetime.combine(date_from, time.min))
    if date_to:
        conditions.append(StoredFile.uploaded_at <= datetime.combine(date_to, time.max))
    if duplicate_status == "duplicate":
        conditions.append(StoredFile.is_duplicate.is_(True))
    elif duplicate_status == "original":
        conditions.append(StoredFile.duplicate_group_id.is_not(None))
        conditions.append(StoredFile.is_duplicate.is_(False))
    elif duplicate_status == "unique":
        conditions.append(StoredFile.duplicate_group_id.is_(None))
        conditions.append(StoredFile.status == "ready")

    total = db.scalar(select(func.count(StoredFile.id)).where(*conditions)) or 0
    column = SORT_COLUMNS[sort_by]
    ordering = column.asc() if sort_order == "asc" else column.desc()
    rows = db.scalars(
        select(StoredFile)
        .where(*conditions)
        .options(selectinload(StoredFile.hash))
        .order_by(ordering, StoredFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return make_page([FileOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/{file_id}", response_model=FileDetail)
def get_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = get_owned_file(db, file_id, user)
    return _build_detail(db, record)


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = get_owned_file(db, file_id, user)
    path = storage.absolute_path(record.stored_path)
    if not path.is_file():
        logger.error("File %s is missing on disk: %s", record.id, path)
        raise NotFoundError("File content is missing from storage")
    record_audit(
        db, "file.download", user_id=user.id, entity_type="file", entity_id=record.id, ip_address=client_ip(request)
    )
    db.commit()
    return FileResponse(
        path,
        filename=record.original_filename,
        media_type="application/octet-stream",  # always force download; never render user content
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{file_id}/delete-preview", response_model=DeletePreview)
def delete_preview(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Show what deleting this file would do, before the user confirms."""
    record = get_owned_file(db, file_id, user)
    copies_remaining = max(record.group.file_count - 1, 0) if record.group else 0
    is_last_copy = copies_remaining == 0
    if record.is_protected:
        message = "This file is protected and cannot be deleted. Remove protection first."
    elif is_last_copy:
        message = "This is the only copy of this content. Deleting it removes the data permanently."
    elif record.is_duplicate:
        message = f"This is a redundant copy. {copies_remaining} other cop{'y' if copies_remaining == 1 else 'ies'} will remain."
    else:
        message = f"This is the original file. {copies_remaining} duplicate(s) will remain and the oldest becomes the new original."
    return DeletePreview(
        file_id=record.id,
        filename=record.original_filename,
        size_bytes=record.size_bytes,
        is_protected=record.is_protected,
        is_duplicate=record.is_duplicate,
        group_id=record.duplicate_group_id,
        copies_remaining=copies_remaining,
        is_last_copy=is_last_copy,
        storage_freed=record.size_bytes,
        can_delete=not record.is_protected,
        message=message,
    )


@router.delete("/{file_id}", response_model=DeleteResponse)
def delete_file(
    file_id: int,
    request: Request,
    confirm: bool = Query(False, description="Must be true to actually delete"),
    reason: str | None = Query(None, max_length=255),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = get_owned_file(db, file_id, user)
    if not confirm:
        raise ValidationAppError("Deletion must be confirmed: call again with confirm=true")
    result = delete_files(db, user, [record], reason=reason, ip_address=client_ip(request))
    return DeleteResponse(
        deleted_count=result.deleted_count,
        storage_freed=result.storage_freed,
        skipped_protected=result.skipped_protected,
    )


@router.patch("/{file_id}/protect", response_model=FileOut)
def set_protection(
    file_id: int,
    payload: ProtectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = get_owned_file(db, file_id, user)
    record.is_protected = payload.is_protected
    record_audit(
        db,
        "file.protect" if payload.is_protected else "file.unprotect",
        user_id=user.id,
        entity_type="file",
        entity_id=record.id,
        ip_address=client_ip(request),
    )
    db.commit()
    return record


@router.post("/{file_id}/reprocess", response_model=FileOut)
def reprocess_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-queue hashing, e.g. for files left 'pending' or 'failed'."""
    record = get_owned_file(db, file_id, user)
    record.status = "pending"
    record.error_message = None
    db.commit()
    enqueue_process_file(record.id)
    db.refresh(record)
    return record
