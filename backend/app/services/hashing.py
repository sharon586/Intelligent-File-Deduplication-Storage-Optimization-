"""Streaming SHA-256 hashing. Files are read in fixed-size chunks, never fully loaded into memory."""
import hashlib
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings


def hash_stream(stream: BinaryIO, chunk_size: int | None = None) -> str:
    chunk_size = chunk_size or settings.HASH_CHUNK_SIZE
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def hash_file(path: str | Path, chunk_size: int | None = None) -> str:
    with open(path, "rb") as fh:
        return hash_stream(fh, chunk_size)
