from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Microsecond precision on MySQL so "earliest upload" ordering is reliable.
UTCDateTime = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def utcnow() -> datetime:
    """Naive UTC timestamp (what MySQL DATETIME columns store)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    files: Mapped[list["StoredFile"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"
    __table_args__ = (UniqueConstraint("owner_id", "sha256", name="uq_duplicate_groups_owner_sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)  # size of one copy
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, default=0)  # storage consumed by all copies
    potential_savings: Mapped[int] = mapped_column(BigInteger, default=0)  # all copies except the original
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    files: Mapped[list["StoredFile"]] = relationship(back_populates="group")


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_owner_uploaded", "owner_id", "uploaded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))  # relative to UPLOAD_DIR, never user controlled
    extension: Mapped[str] = mapped_column(String(20), default="", index=True)
    content_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream")
    category: Mapped[str] = mapped_column(String(20), default="other", index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|processing|ready|failed
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # True for non-original copies
    duplicate_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    owner: Mapped[User] = relationship(back_populates="files")
    group: Mapped[DuplicateGroup | None] = relationship(back_populates="files")
    hash: Mapped["FileHash | None"] = relationship(
        back_populates="file", uselist=False, cascade="all, delete-orphan"
    )
    file_metadata: Mapped["FileMetadata | None"] = relationship(
        back_populates="file", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def sha256(self) -> str | None:
        return self.hash.sha256 if self.hash else None


class FileHash(Base):
    __tablename__ = "file_hashes"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    algorithm: Mapped[str] = mapped_column(String(20), default="sha256")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    file: Mapped[StoredFile] = relationship(back_populates="hash")


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), unique=True)
    detected_mime: Mapped[str | None] = mapped_column(String(150), nullable=True)
    extension: Mapped[str] = mapped_column(String(20), default="")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    file: Mapped[StoredFile] = relationship(back_populates="file_metadata")


class DeletionHistory(Base):
    """Snapshot of a deleted file. file_id is intentionally not a foreign key: the file row is gone."""

    __tablename__ = "deletion_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_freed: Mapped[int] = mapped_column(BigInteger, default=0)
    was_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
