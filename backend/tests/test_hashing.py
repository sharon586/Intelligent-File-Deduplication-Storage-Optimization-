import hashlib
import io

from app.services.hashing import hash_file, hash_stream


def test_hash_matches_hashlib(tmp_path):
    data = b"hello duplicate world" * 1000
    path = tmp_path / "a.bin"
    path.write_bytes(data)
    assert hash_file(path) == hashlib.sha256(data).hexdigest()


def test_chunk_size_does_not_change_digest(tmp_path):
    data = bytes(range(256)) * 5000
    path = tmp_path / "b.bin"
    path.write_bytes(data)
    assert hash_file(path, chunk_size=7) == hash_file(path, chunk_size=1024 * 1024)


def test_identical_content_different_names_same_hash(tmp_path):
    (tmp_path / "report.pdf").write_bytes(b"same content")
    (tmp_path / "totally_different_name.txt").write_bytes(b"same content")
    assert hash_file(tmp_path / "report.pdf") == hash_file(tmp_path / "totally_different_name.txt")


def test_different_content_different_hash(tmp_path):
    (tmp_path / "a").write_bytes(b"content A")
    (tmp_path / "b").write_bytes(b"content B")
    assert hash_file(tmp_path / "a") != hash_file(tmp_path / "b")


def test_hash_stream_large_input_is_chunked():
    data = b"x" * (3 * 1024 * 1024 + 123)
    assert hash_stream(io.BytesIO(data), chunk_size=64 * 1024) == hashlib.sha256(data).hexdigest()
