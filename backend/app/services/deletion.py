"""Safe deletion of files with protection checks, history and group maintenance."""
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.models import DeletionHistory, StoredFile, User
from app.services import storage
from app.services.audit import record_audit
from app.services.duplicates import refresh_group

logger = logging.getLogger(__name__)


@dataclass
class DeleteResult:
    deleted_count: int = 0
    storage_freed: int = 0
    skipped_protected: list[int] = field(default_factory=list)


def delete_files(
    db: Session,
    user: User,
    files: list[StoredFile],
    reason: str | None = None,
    ip_address: str | None = None,
    skip_protected: bool = False,
) -> DeleteResult:
    """Delete files owned by `user`. Protected files raise ForbiddenError unless skip_protected is set."""
    result = DeleteResult()
    paths_to_remove: list[str] = []
    group_ids: set[int] = set()

    for f in files:
        if f.owner_id != user.id:
            raise ForbiddenError("You do not have access to this file")
        if f.is_protected:
            if skip_protected:
                result.skipped_protected.append(f.id)
                continue
            raise ForbiddenError(f"'{f.original_filename}' is protected and cannot be deleted")

        db.add(
            DeletionHistory(
                user_id=user.id,
                file_id=f.id,
                filename=f.original_filename,
                sha256=f.sha256,
                size_bytes=f.size_bytes,
                storage_freed=f.size_bytes,
                was_duplicate=f.is_duplicate,
                group_id=f.duplicate_group_id,
                reason=reason,
            )
        )
        record_audit(
            db,
            "file.delete",
            user_id=user.id,
            entity_type="file",
            entity_id=f.id,
            details={"filename": f.original_filename, "size_bytes": f.size_bytes, "was_duplicate": f.is_duplicate},
            ip_address=ip_address,
        )
        if f.duplicate_group_id is not None:
            group_ids.add(f.duplicate_group_id)
        paths_to_remove.append(f.stored_path)
        result.deleted_count += 1
        result.storage_freed += f.size_bytes
        db.delete(f)

    db.flush()
    for gid in group_ids:
        refresh_group(db, gid)
    db.commit()

    # Remove bytes from disk only after the database change is durable.
    for path in paths_to_remove:
        storage.remove_file(path)
    return result
