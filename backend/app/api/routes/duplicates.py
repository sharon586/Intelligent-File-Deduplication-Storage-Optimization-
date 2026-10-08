import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.exceptions import NotFoundError, ValidationAppError
from app.db.session import get_db
from app.models import DuplicateGroup, StoredFile, User
from app.schemas.common import Page, make_page
from app.schemas.file import CleanupRequest, DeleteResponse, DuplicateGroupOut, FileBrief, RescanResponse
from app.services.audit import record_audit
from app.services.deletion import delete_files
from app.services.queue import enqueue_rescan

router = APIRouter(prefix="/duplicates", tags=["Duplicates"])
logger = logging.getLogger(__name__)

SORT_COLUMNS = {
    "savings": DuplicateGroup.potential_savings,
    "size": DuplicateGroup.file_size,
    "count": DuplicateGroup.file_count,
    "created": DuplicateGroup.created_at,
}


def _serialize_groups(db: Session, groups: list[DuplicateGroup]) -> list[DuplicateGroupOut]:
    if not groups:
        return []
    files = db.scalars(
        select(StoredFile)
        .where(StoredFile.duplicate_group_id.in_([g.id for g in groups]))
        .order_by(StoredFile.uploaded_at, StoredFile.id)
    ).all()
    by_group: dict[int, list[StoredFile]] = {}
    for f in files:
        by_group.setdefault(f.duplicate_group_id, []).append(f)  # type: ignore[arg-type]

    result = []
    for g in groups:
        members = by_group.get(g.id, [])
        original = next((f for f in members if not f.is_duplicate), None)
        copies = [f for f in members if f.is_duplicate]
        result.append(
            DuplicateGroupOut(
                id=g.id,
                sha256=g.sha256,
                file_size=g.file_size,
                file_count=g.file_count,
                storage_consumed=g.total_size,
                potential_savings=g.potential_savings,
                created_at=g.created_at,
                original=FileBrief.model_validate(original) if original else None,
                duplicates=[FileBrief.model_validate(c) for c in copies],
            )
        )
    return result


def _get_group(db: Session, group_id: int, user: User) -> DuplicateGroup:
    group = db.get(DuplicateGroup, group_id)
    if group is None or group.owner_id != user.id:
        raise NotFoundError("Duplicate group not found")
    return group


@router.get("/groups", response_model=Page[DuplicateGroupOut])
def list_groups(
    sort_by: Literal["savings", "size", "count", "created"] = "savings",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count(DuplicateGroup.id)).where(DuplicateGroup.owner_id == user.id)) or 0
    column = SORT_COLUMNS[sort_by]
    groups = db.scalars(
        select(DuplicateGroup)
        .where(DuplicateGroup.owner_id == user.id)
        .order_by(column.asc() if sort_order == "asc" else column.desc(), DuplicateGroup.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return make_page(_serialize_groups(db, list(groups)), total, page, page_size)


@router.get("/groups/{group_id}", response_model=DuplicateGroupOut)
def get_group(group_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _serialize_groups(db, [_get_group(db, group_id, user)])[0]


@router.post("/groups/{group_id}/cleanup", response_model=DeleteResponse)
def cleanup_group(
    group_id: int,
    payload: CleanupRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete every redundant copy in a group, keeping the original. Protected copies are skipped."""
    group = _get_group(db, group_id, user)
    if not payload.confirm:
        raise ValidationAppError("Cleanup must be confirmed: send {\"confirm\": true}")
    copies = list(
        db.scalars(
            select(StoredFile).where(StoredFile.duplicate_group_id == group.id, StoredFile.is_duplicate.is_(True))
        )
    )
    result = delete_files(
        db,
        user,
        copies,
        reason="Duplicate group cleanup",
        ip_address=client_ip(request),
        skip_protected=True,
    )
    record_audit(
        db,
        "group.cleanup",
        user_id=user.id,
        entity_type="duplicate_group",
        entity_id=group_id,
        details={"deleted": result.deleted_count, "storage_freed": result.storage_freed},
        ip_address=client_ip(request),
    )
    db.commit()
    return DeleteResponse(
        deleted_count=result.deleted_count,
        storage_freed=result.storage_freed,
        skipped_protected=result.skipped_protected,
    )


@router.post("/rescan", response_model=RescanResponse)
def rescan(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Rebuild all duplicate groups in the background."""
    queued = enqueue_rescan(user.id)
    record_audit(db, "group.rescan", user_id=user.id, ip_address=client_ip(request), details={"queued": queued})
    db.commit()
    return RescanResponse(
        message="Rescan started" if queued else "Background queue is unavailable; try again shortly",
        queued=queued,
    )
