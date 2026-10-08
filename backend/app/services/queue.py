"""Thin wrappers around Celery dispatch so API code never crashes when the broker is down."""
import logging

logger = logging.getLogger(__name__)


def enqueue_process_file(file_id: int) -> bool:
    from app.worker.tasks import process_file

    try:
        process_file.delay(file_id)
        return True
    except Exception:  # noqa: BLE001 - broker problems must not fail the upload
        logger.exception("Could not queue hashing task for file %s (file stays 'pending')", file_id)
        return False


def enqueue_rescan(user_id: int) -> bool:
    from app.worker.tasks import rescan_user

    try:
        rescan_user.delay(user_id)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue rescan for user %s", user_id)
        return False
