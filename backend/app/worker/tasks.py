import logging

from app.core.logging import setup_logging
from app.core.config import settings
from app.db import session as db_session
from app.services.duplicates import rebuild_user_groups
from app.services.processing import process_file_record
from app.worker.celery_app import celery_app

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@celery_app.task(name="dedup.process_file")
def process_file(file_id: int) -> dict:
    """Hash an uploaded file in chunks and update duplicate groups."""
    with db_session.SessionLocal() as db:
        record = process_file_record(db, file_id)
        if record is None:
            return {"file_id": file_id, "status": "missing"}
        return {"file_id": file_id, "status": record.status, "is_duplicate": record.is_duplicate}


@celery_app.task(name="dedup.rescan_user")
def rescan_user(user_id: int) -> dict:
    """Rebuild every duplicate group for one user from stored hashes."""
    with db_session.SessionLocal() as db:
        groups = rebuild_user_groups(db, user_id)
    logger.info("Rescan finished for user %s: %s groups", user_id, groups)
    return {"user_id": user_id, "groups": groups}
