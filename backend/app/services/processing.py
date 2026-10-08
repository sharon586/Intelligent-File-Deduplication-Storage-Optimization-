"""Hash a stored file and register it in the duplicate index (run by the Celery worker)."""
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import FileHash, StoredFile, utcnow
from app.services import storage
from app.services.duplicates import assign_to_group
from app.services.hashing import hash_file

logger = logging.getLogger(__name__)


def process_file_record(db: Session, file_id: int) -> StoredFile | None:
    record = db.get(StoredFile, file_id)
    if record is None:
        logger.warning("process_file: file %s no longer exists", file_id)
        return None

    record.status = "processing"
    record.error_message = None
    db.commit()

    try:
        path = storage.absolute_path(record.stored_path)
        digest = hash_file(path, settings.HASH_CHUNK_SIZE)
        size = path.stat().st_size

        record.size_bytes = size
        if record.hash is None:
            record.hash = FileHash(sha256=digest, size_bytes=size)
        else:
            record.hash.sha256 = digest
            record.hash.size_bytes = size
            record.hash.computed_at = utcnow()
        db.flush()

        assign_to_group(db, record, digest)

        record.status = "ready"
        record.processed_at = utcnow()
        db.commit()
        logger.info("Processed file %s sha256=%s duplicate=%s", file_id, digest, record.is_duplicate)
    except Exception as exc:  # noqa: BLE001 - any failure must be recorded on the file
        db.rollback()
        logger.exception("Failed to process file %s", file_id)
        failed = db.get(StoredFile, file_id)
        if failed is not None:
            failed.status = "failed"
            failed.error_message = str(exc)[:500]
            db.commit()
            return failed
        return None

    db.refresh(record)
    return record
