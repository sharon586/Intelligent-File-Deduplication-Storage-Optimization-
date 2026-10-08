from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, DeletionHistory, DuplicateGroup, StoredFile, User, utcnow
from app.schemas.analytics import (
    AnalyticsSummary,
    AuditLogOut,
    CategoryStat,
    DailyUpload,
    DeletionHistoryOut,
)
from app.schemas.common import Page, make_page
from app.schemas.file import FileBrief

router = APIRouter(tags=["Analytics & History"])


@router.get("/analytics/summary", response_model=AnalyticsSummary)
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned = StoredFile.owner_id == user.id

    total_files, total_storage = db.execute(
        select(func.count(StoredFile.id), func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(owned)
    ).one()
    duplicate_files = db.scalar(select(func.count(StoredFile.id)).where(owned, StoredFile.is_duplicate.is_(True))) or 0
    duplicate_storage = db.scalar(
        select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(owned, StoredFile.duplicate_group_id.is_not(None))
    ) or 0
    groups, savings = db.execute(
        select(func.count(DuplicateGroup.id), func.coalesce(func.sum(DuplicateGroup.potential_savings), 0)).where(
            DuplicateGroup.owner_id == user.id
        )
    ).one()
    pending = db.scalar(
        select(func.count(StoredFile.id)).where(owned, StoredFile.status.in_(["pending", "processing"]))
    ) or 0

    largest = db.scalars(select(StoredFile).where(owned).order_by(StoredFile.size_bytes.desc(), StoredFile.id).limit(5)).all()
    recent = db.scalars(select(StoredFile).where(owned).order_by(StoredFile.uploaded_at.desc(), StoredFile.id.desc()).limit(5)).all()

    categories = db.execute(
        select(StoredFile.category, func.count(StoredFile.id), func.coalesce(func.sum(StoredFile.size_bytes), 0))
        .where(owned)
        .group_by(StoredFile.category)
        .order_by(func.sum(StoredFile.size_bytes).desc())
    ).all()

    since = (utcnow() - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_rows = db.execute(
        select(func.date(StoredFile.uploaded_at), func.count(StoredFile.id))
        .where(owned, StoredFile.uploaded_at >= since)
        .group_by(func.date(StoredFile.uploaded_at))
    ).all()
    counts = {str(day): count for day, count in daily_rows}
    uploads_by_day = []
    for i in range(14):
        day = (since + timedelta(days=i)).date().isoformat()
        uploads_by_day.append(DailyUpload(date=day, count=counts.get(day, 0)))

    total_storage = int(total_storage)
    savings = int(savings)
    return AnalyticsSummary(
        total_files=total_files,
        total_storage=total_storage,
        duplicate_files=duplicate_files,
        duplicate_storage=int(duplicate_storage),
        duplicate_groups=groups,
        potential_savings=savings,
        savings_percent=round(savings / total_storage * 100, 2) if total_storage else 0.0,
        pending_files=pending,
        largest_files=[FileBrief.model_validate(f) for f in largest],
        recent_uploads=[FileBrief.model_validate(f) for f in recent],
        by_category=[CategoryStat(category=c, count=n, size_bytes=int(s)) for c, n, s in categories],
        uploads_by_day=uploads_by_day,
    )


@router.get("/history/deletions", response_model=Page[DeletionHistoryOut])
def deletion_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count(DeletionHistory.id)).where(DeletionHistory.user_id == user.id)) or 0
    rows = db.scalars(
        select(DeletionHistory)
        .where(DeletionHistory.user_id == user.id)
        .order_by(DeletionHistory.deleted_at.desc(), DeletionHistory.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return make_page([DeletionHistoryOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/history/audit", response_model=Page[AuditLogOut])
def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.user_id == user.id)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return make_page([AuditLogOut.model_validate(r) for r in rows], total, page, page_size)
