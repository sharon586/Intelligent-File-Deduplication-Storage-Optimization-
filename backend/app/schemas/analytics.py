from pydantic import BaseModel, ConfigDict

from app.schemas.common import UTCDateTime
from app.schemas.file import FileBrief


class CategoryStat(BaseModel):
    category: str
    count: int
    size_bytes: int


class DailyUpload(BaseModel):
    date: str
    count: int


class AnalyticsSummary(BaseModel):
    total_files: int
    total_storage: int
    duplicate_files: int  # redundant copies (non-original files)
    duplicate_storage: int  # storage used by every file that belongs to a duplicate group
    duplicate_groups: int
    potential_savings: int  # storage that could be freed by removing redundant copies
    savings_percent: float
    pending_files: int
    largest_files: list[FileBrief]
    recent_uploads: list[FileBrief]
    by_category: list[CategoryStat]
    uploads_by_day: list[DailyUpload]


class DeletionHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int | None
    filename: str
    sha256: str | None
    size_bytes: int
    storage_freed: int
    was_duplicate: bool
    group_id: int | None
    reason: str | None
    deleted_at: UTCDateTime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity_type: str | None
    entity_id: int | None
    details: dict | None
    ip_address: str | None
    created_at: UTCDateTime

