from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UTCDateTime

FileStatus = Literal["pending", "processing", "ready", "failed"]


class FileBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    size_bytes: int
    uploaded_at: UTCDateTime
    is_protected: bool


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    extension: str
    content_type: str
    category: str
    size_bytes: int
    status: FileStatus
    is_protected: bool
    is_duplicate: bool
    duplicate_group_id: int | None
    sha256: str | None
    uploaded_at: UTCDateTime
    processed_at: UTCDateTime | None


class MetadataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detected_mime: str | None
    extension: str
    extra: dict | None


class GroupSummary(BaseModel):
    id: int
    file_count: int
    file_size: int
    potential_savings: int
    original_file_id: int | None
    original_filename: str | None


class FileDetail(FileOut):
    error_message: str | None
    file_metadata: MetadataOut | None = None
    group: GroupSummary | None = None


class ProtectRequest(BaseModel):
    is_protected: bool


class DeletePreview(BaseModel):
    file_id: int
    filename: str
    size_bytes: int
    is_protected: bool
    is_duplicate: bool
    group_id: int | None
    copies_remaining: int
    is_last_copy: bool
    storage_freed: int
    can_delete: bool
    message: str


class DeleteResponse(BaseModel):
    deleted_count: int
    storage_freed: int
    skipped_protected: list[int] = []


class DuplicateGroupOut(BaseModel):
    id: int
    sha256: str
    file_size: int
    file_count: int
    storage_consumed: int
    potential_savings: int
    created_at: UTCDateTime
    original: FileBrief | None
    duplicates: list[FileBrief]


class CleanupRequest(BaseModel):
    confirm: bool = False


class RescanResponse(BaseModel):
    message: str
    queued: bool

