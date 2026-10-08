"""Unit tests for duplicate detection, grouping and safe deletion."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import ForbiddenError
from app.core.security import hash_password
from app.models import DeletionHistory, DuplicateGroup, StoredFile, User, utcnow
from app.services import storage
from app.services.deletion import delete_files
from app.services.duplicates import calculate_group_stats, pick_original, rebuild_user_groups
from app.services.processing import process_file_record


def make_user(db, name="alice") -> User:
    user = User(username=name, email=f"{name}@example.com", hashed_password=hash_password("password123"))
    db.add(user)
    db.commit()
    return user


_counter = {"n": 0}


def add_file(db, user, name, content: bytes, minutes_ago: int = 0, process: bool = True) -> StoredFile:
    _counter["n"] += 1
    rel = f"{user.id}/test-{_counter['n']}"
    path = storage.absolute_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record = StoredFile(
        owner_id=user.id,
        original_filename=name,
        stored_path=rel,
        extension=name.rpartition(".")[2],
        size_bytes=len(content),
        status="pending",
        uploaded_at=utcnow() - timedelta(minutes=minutes_ago),
    )
    db.add(record)
    db.commit()
    if process:
        process_file_record(db, record.id)
        db.refresh(record)
    return record


def test_identical_content_with_different_names_is_grouped(db):
    user = make_user(db)
    a = add_file(db, user, "report.pdf", b"same bytes", minutes_ago=10)
    b = add_file(db, user, "copy_of_report (1).bak", b"same bytes", minutes_ago=5)

    db.refresh(a)
    assert a.status == "ready" and b.status == "ready"
    assert a.sha256 == b.sha256
    assert a.duplicate_group_id == b.duplicate_group_id is not None
    assert a.is_duplicate is False  # earliest upload is the original
    assert b.is_duplicate is True


def test_group_storage_numbers(db):
    user = make_user(db)
    content = b"x" * 1000
    add_file(db, user, "one.txt", content, minutes_ago=30)
    add_file(db, user, "two.txt", content, minutes_ago=20)
    add_file(db, user, "three.txt", content, minutes_ago=10)

    group = db.scalar(select(DuplicateGroup))
    assert group.file_count == 3
    assert group.file_size == 1000
    assert group.total_size == 3000
    assert group.potential_savings == 2000


def test_unique_files_are_not_grouped(db):
    user = make_user(db)
    a = add_file(db, user, "a.txt", b"alpha")
    b = add_file(db, user, "b.txt", b"beta")
    assert a.duplicate_group_id is None and b.duplicate_group_id is None
    assert db.scalar(select(DuplicateGroup)) is None


def test_same_content_for_different_users_is_not_a_duplicate(db):
    alice, bob = make_user(db, "alice"), make_user(db, "bob")
    a = add_file(db, alice, "a.txt", b"shared")
    b = add_file(db, bob, "a.txt", b"shared")
    assert a.duplicate_group_id is None and b.duplicate_group_id is None


def test_reprocessing_is_idempotent(db):
    user = make_user(db)
    a = add_file(db, user, "a.txt", b"data", minutes_ago=5)
    b = add_file(db, user, "b.txt", b"data", minutes_ago=1)
    process_file_record(db, b.id)
    process_file_record(db, a.id)
    groups = db.scalars(select(DuplicateGroup)).all()
    assert len(groups) == 1 and groups[0].file_count == 2


def test_pick_original_and_stats_helpers():
    now = utcnow()
    old = StoredFile(id=5, size_bytes=10, uploaded_at=now - timedelta(days=1))
    new = StoredFile(id=2, size_bytes=10, uploaded_at=now)
    assert pick_original([new, old]) is old
    assert calculate_group_stats([new, old]) == {
        "file_count": 2,
        "file_size": 10,
        "total_size": 20,
        "potential_savings": 10,
    }
    assert calculate_group_stats([])["file_count"] == 0


def test_deleting_duplicate_dissolves_pair_group(db):
    user = make_user(db)
    a = add_file(db, user, "a.txt", b"data", minutes_ago=5)
    b = add_file(db, user, "b.txt", b"data", minutes_ago=1)

    result = delete_files(db, user, [b], reason="test")
    assert result.deleted_count == 1 and result.storage_freed == 4

    db.refresh(a)
    assert a.duplicate_group_id is None and a.is_duplicate is False
    assert db.scalar(select(DuplicateGroup)) is None
    history = db.scalar(select(DeletionHistory))
    assert history.filename == "b.txt" and history.was_duplicate is True and history.storage_freed == 4
    assert not storage.absolute_path(b.stored_path).exists()


def test_deleting_original_promotes_next_oldest(db):
    user = make_user(db)
    a = add_file(db, user, "a.txt", b"data", minutes_ago=30)
    b = add_file(db, user, "b.txt", b"data", minutes_ago=20)
    c = add_file(db, user, "c.txt", b"data", minutes_ago=10)

    delete_files(db, user, [a])
    db.refresh(b)
    db.refresh(c)
    assert b.is_duplicate is False and c.is_duplicate is True
    group = db.scalar(select(DuplicateGroup))
    assert group.file_count == 2 and group.potential_savings == 4


def test_protected_file_cannot_be_deleted(db):
    user = make_user(db)
    a = add_file(db, user, "a.txt", b"data", minutes_ago=5)
    b = add_file(db, user, "b.txt", b"data", minutes_ago=1)
    b.is_protected = True
    db.commit()

    with pytest.raises(ForbiddenError):
        delete_files(db, user, [b])
    assert db.get(StoredFile, b.id) is not None
    assert storage.absolute_path(b.stored_path).exists()

    skipped = delete_files(db, user, [b], skip_protected=True)
    assert skipped.deleted_count == 0 and skipped.skipped_protected == [b.id]
    assert db.get(StoredFile, a.id) is not None


def test_cannot_delete_another_users_file(db):
    alice, bob = make_user(db, "alice"), make_user(db, "bob")
    f = add_file(db, alice, "a.txt", b"data")
    with pytest.raises(ForbiddenError):
        delete_files(db, bob, [f])


def test_rebuild_groups_recreates_groups_from_hashes(db):
    user = make_user(db)
    add_file(db, user, "a.txt", b"data", minutes_ago=5)
    add_file(db, user, "b.txt", b"data", minutes_ago=3)
    add_file(db, user, "c.txt", b"unique")
    for g in db.scalars(select(DuplicateGroup)).all():
        db.delete(g)
    db.commit()

    assert rebuild_user_groups(db, user.id) == 1
    group = db.scalar(select(DuplicateGroup))
    assert group.file_count == 2 and group.potential_savings == 4


def test_missing_file_on_disk_marks_failed(db):
    user = make_user(db)
    rec = add_file(db, user, "gone.txt", b"data", process=False)
    storage.absolute_path(rec.stored_path).unlink()
    result = process_file_record(db, rec.id)
    assert result.status == "failed" and result.error_message
