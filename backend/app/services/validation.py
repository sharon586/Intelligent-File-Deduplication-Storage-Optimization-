"""Upload validation: filename sanitising, extension blocklist and content-signature checks."""
import mimetypes
import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import ValidationAppError

CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "image": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "tiff", "ico", "heic"},
    "document": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "rtf", "csv", "odt", "ods", "json", "xml"},
    "video": {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v"},
    "audio": {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"},
    "code": {"py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "cs", "go", "rs", "html", "css", "sql", "yml", "yaml"},
}
CATEGORIES = [*CATEGORY_EXTENSIONS.keys(), "other"]

# Magic-number signatures for formats where a mismatch is a strong sign of a disguised file.
_SIGNATURES: list[tuple[str, bytes]] = [
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpeg", b"\xff\xd8\xff"),
    ("gif", b"GIF87a"),
    ("gif", b"GIF89a"),
    ("pdf", b"%PDF-"),
    ("zip", b"PK\x03\x04"),
    ("zip", b"PK\x05\x06"),
    ("exe", b"MZ"),
    ("elf", b"\x7fELF"),
]
_EXPECTED_SIGNATURE = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "gif": "gif",
    "pdf": "pdf",
    "zip": "zip",
    "docx": "zip",
    "xlsx": "zip",
    "pptx": "zip",
}
_SIGNATURE_MIME = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "pdf": "application/pdf",
    "zip": "application/zip",
}
_DANGEROUS_SIGNATURES = {"exe", "elf"}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class UploadInfo:
    filename: str
    extension: str
    category: str
    content_type: str
    detected_type: str | None


def sanitize_filename(name: str) -> str:
    """Strip any path components and control characters; cap the length at 255."""
    name = _CONTROL_CHARS.sub("", name or "")
    name = name.replace("\\", "/").split("/")[-1].strip().strip(".")
    if not name:
        raise ValidationAppError("Invalid or empty filename")
    if len(name) > 255:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 20:
            name = stem[: 255 - len(ext) - 1] + "." + ext
        else:
            name = name[:255]
    return name


def get_extension(filename: str) -> str:
    _, dot, ext = filename.rpartition(".")
    return ext.lower()[:20] if dot else ""


def categorize(extension: str) -> str:
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if extension in extensions:
            return category
    return "other"


def detect_signature(header: bytes) -> str | None:
    for name, magic in _SIGNATURES:
        if header.startswith(magic):
            return name
    return None


def validate_upload(raw_filename: str, header: bytes) -> UploadInfo:
    filename = sanitize_filename(raw_filename)
    extension = get_extension(filename)

    if extension in settings.blocked_extensions_set:
        raise ValidationAppError(f"Files with the '.{extension}' extension are not allowed")

    detected = detect_signature(header)
    if detected in _DANGEROUS_SIGNATURES:
        raise ValidationAppError("Executable files are not allowed")

    expected = _EXPECTED_SIGNATURE.get(extension)
    if expected and detected != expected:
        raise ValidationAppError(
            f"File content does not match its '.{extension}' extension"
        )

    guessed, _ = mimetypes.guess_type(filename)
    content_type = guessed or _SIGNATURE_MIME.get(detected or "", "application/octet-stream")
    return UploadInfo(
        filename=filename,
        extension=extension,
        category=categorize(extension),
        content_type=content_type,
        detected_type=detected,
    )
