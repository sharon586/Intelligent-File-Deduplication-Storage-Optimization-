import pytest

from app.core.exceptions import ValidationAppError
from app.services.validation import categorize, sanitize_filename, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_sanitize_strips_paths_and_control_chars():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\Users\\me\\doc.txt") == "doc.txt"
    assert sanitize_filename("na\x00me.txt") == "name.txt"


def test_sanitize_rejects_empty():
    with pytest.raises(ValidationAppError):
        sanitize_filename("   ")


def test_sanitize_caps_length_keeping_extension():
    name = sanitize_filename("a" * 400 + ".png")
    assert len(name) <= 255 and name.endswith(".png")


def test_blocked_extension_rejected():
    with pytest.raises(ValidationAppError):
        validate_upload("setup.exe", b"anything")


def test_executable_signature_rejected_even_with_safe_extension():
    with pytest.raises(ValidationAppError):
        validate_upload("holiday.txt", b"MZ\x90\x00\x03")


def test_extension_signature_mismatch_rejected():
    with pytest.raises(ValidationAppError):
        validate_upload("photo.png", b"just text pretending to be a png")


def test_valid_png_accepted():
    info = validate_upload("photo.PNG", PNG)
    assert info.extension == "png"
    assert info.category == "image"
    assert info.content_type == "image/png"


def test_plain_text_accepted():
    info = validate_upload("notes.txt", b"hello")
    assert info.category == "document"


def test_categorize_unknown_is_other():
    assert categorize("xyz") == "other"
