"""Disk storage helpers. All paths are generated server-side; user filenames are never used on disk."""
import logging
import os
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError

logger = logging.getLogger(__name__)


def absolute_path(relative_path: str) -> Path:
    root = settings.upload_root
    full = (root / relative_path).resolve()
    if root not in full.parents:
        raise NotFoundError("File not found")  # path traversal attempt or corrupted record
    return full


def save_stream(first_chunk: bytes, stream: BinaryIO, owner_id: int) -> tuple[str, int]:
    """Write an upload to disk chunk by chunk. Returns (relative_path, size_in_bytes)."""
    owner_dir = settings.upload_root / str(owner_id)
    owner_dir.mkdir(parents=True, exist_ok=True)
    relative = f"{owner_id}/{uuid.uuid4().hex}"
    target = owner_dir / relative.split("/")[1]

    size = 0
    limit = settings.max_upload_bytes
    try:
        with open(target, "wb") as out:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLargeError(
                        f"File exceeds the maximum upload size of {settings.MAX_UPLOAD_SIZE_MB} MB"
                    )
                out.write(chunk)
                chunk = stream.read(settings.HASH_CHUNK_SIZE)
    except BaseException:
        _safe_unlink(target)
        raise
    return relative, size


def remove_file(relative_path: str) -> None:
    try:
        _safe_unlink(absolute_path(relative_path))
    except NotFoundError:
        logger.warning("Refusing to delete path outside upload root: %s", relative_path)


def _safe_unlink(path: Path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not remove file %s", path)
