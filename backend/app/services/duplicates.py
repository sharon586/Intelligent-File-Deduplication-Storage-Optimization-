"""Duplicate detection and grouping logic.

Two files are duplicates when they belong to the same user and have the same SHA-256 digest,
regardless of filename, upload time or location. The earliest upload in a group is the "original".
"""
import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DuplicateGroup, FileHash, StoredFile

logger = logging.getLogger(__name__)


def pick_original(files: list[StoredFile]) -> StoredFile:
    """Original = earliest upload; ties are broken by the lowest id."""
    return min(files, key=lambda f: (f.uploaded_at, f.id))


def calculate_group_stats(files: list[StoredFile]) -> dict[str, int]:
    """Pure helper: storage numbers for a set of identical files."""
    if not files:
        return {"file_count": 0, "file_size": 0, "total_size": 0, "potential_savings": 0}
    original = pick_original(files)
    total = sum(f.size_bytes for f in files)
    return {
        "file_count": len(files),
        "file_size": original.size_bytes,
        "total_size": total,
        "potential_savings": total - original.size_bytes,
    }


def refresh_group(db: Session, group_id: int | None) -> DuplicateGroup | None:
    """Recompute originals and stats for a group; dissolve it when fewer than 2 files remain."""
    if group_id is None:
        return None
    group = db.get(DuplicateGroup, group_id)
    if group is None:
        return None

    db.flush()
    files = list(
        db.scalars(
            select(StoredFile)
            .where(StoredFile.duplicate_group_id == group_id)
            .order_by(StoredFile.uploaded_at, StoredFile.id)
        )
    )
    if len(files) < 2:
        for f in files:
            f.duplicate_group_id = None
            f.is_duplicate = False
        db.flush()
        db.delete(group)
        db.flush()
        return None

    original = pick_original(files)
    for f in files:
        f.is_duplicate = f.id != original.id
    stats = calculate_group_stats(files)
    group.file_count = stats["file_count"]
    group.file_size = stats["file_size"]
    group.total_size = stats["total_size"]
    group.potential_savings = stats["potential_savings"]
    db.flush()
    return group


def _get_or_create_group(db: Session, owner_id: int, sha256: str) -> DuplicateGroup:
    group = db.scalar(
        select(DuplicateGroup).where(DuplicateGroup.owner_id == owner_id, DuplicateGroup.sha256 == sha256)
    )
    if group:
        return group
    try:
        with db.begin_nested():
            group = DuplicateGroup(owner_id=owner_id, sha256=sha256)
            db.add(group)
            db.flush()
        return group
    except IntegrityError:
        # Another worker created the same group concurrently; use theirs.
        group = db.scalar(
            select(DuplicateGroup).where(DuplicateGroup.owner_id == owner_id, DuplicateGroup.sha256 == sha256)
        )
        if group is None:
            raise
        return group


def assign_to_group(db: Session, file: StoredFile, sha256: str) -> DuplicateGroup | None:
    """Place a freshly hashed file into the right duplicate group (creating it if needed).

    The file's FileHash row must already be flushed so concurrent lookups can see it.
    """
    previous_group_id = file.duplicate_group_id

    peers = list(
        db.scalars(
            select(StoredFile)
            .join(FileHash, FileHash.file_id == StoredFile.id)
            .where(
                StoredFile.owner_id == file.owner_id,
                FileHash.sha256 == sha256,
                StoredFile.id != file.id,
            )
        )
    )

    if not peers:
        file.duplicate_group_id = None
        file.is_duplicate = False
        db.flush()
        if previous_group_id is not None:
            refresh_group(db, previous_group_id)
        return None

    group = _get_or_create_group(db, file.owner_id, sha256)
    file.duplicate_group_id = group.id
    for peer in peers:
        peer.duplicate_group_id = group.id
    db.flush()

    if previous_group_id is not None and previous_group_id != group.id:
        refresh_group(db, previous_group_id)
    return refresh_group(db, group.id)


def rebuild_user_groups(db: Session, user_id: int) -> int:
    """Recompute every duplicate group for a user from the stored hashes. Returns the group count."""
    db.execute(
        update(StoredFile)
        .where(StoredFile.owner_id == user_id)
        .values(duplicate_group_id=None, is_duplicate=False)
    )
    db.execute(delete(DuplicateGroup).where(DuplicateGroup.owner_id == user_id))
    db.flush()

    hashes = db.scalars(
        select(FileHash.sha256)
        .join(StoredFile, StoredFile.id == FileHash.file_id)
        .where(StoredFile.owner_id == user_id, StoredFile.status == "ready")
        .group_by(FileHash.sha256)
        .having(func.count(FileHash.id) > 1)
    ).all()

    for sha in hashes:
        members = list(
            db.scalars(
                select(StoredFile)
                .join(FileHash, FileHash.file_id == StoredFile.id)
                .where(StoredFile.owner_id == user_id, FileHash.sha256 == sha, StoredFile.status == "ready")
            )
        )
        group = _get_or_create_group(db, user_id, sha)
        for m in members:
            m.duplicate_group_id = group.id
        db.flush()
        refresh_group(db, group.id)

    db.commit()
    return len(hashes)
