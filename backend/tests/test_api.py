"""End-to-end API tests (Celery runs eagerly, SQLite stands in for MySQL)."""

API = "/api/v1"


def upload(client, headers, name, content: bytes):
    return client.post(f"{API}/files/upload", headers=headers, files={"file": (name, content)})


def test_register_login_and_me(client):
    r = client.post(f"{API}/auth/register", json={"username": "carol", "email": "carol@example.com", "password": "StrongPass123"})
    assert r.status_code == 201
    dup = client.post(f"{API}/auth/register", json={"username": "carol", "email": "x@example.com", "password": "StrongPass123"})
    assert dup.status_code == 409
    bad = client.post(f"{API}/auth/login", data={"username": "carol", "password": "wrong-password"})
    assert bad.status_code == 401
    ok = client.post(f"{API}/auth/login", data={"username": "carol@example.com", "password": "StrongPass123"})
    assert ok.status_code == 200
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
    assert me.json()["username"] == "carol"


def test_endpoints_require_authentication(client):
    assert client.get(f"{API}/files").status_code == 401
    assert client.get(f"{API}/analytics/summary").status_code == 401
    assert client.get(f"{API}/files", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_upload_detects_duplicates_and_reports_analytics(client, auth_headers):
    content = b"A" * 2048
    r1 = upload(client, auth_headers, "original.txt", content)
    r2 = upload(client, auth_headers, "renamed copy.txt", content)
    r3 = upload(client, auth_headers, "different.txt", b"B" * 100)
    assert r1.status_code == r2.status_code == r3.status_code == 201

    files = client.get(f"{API}/files", headers=auth_headers).json()
    assert files["total"] == 3
    by_name = {f["original_filename"]: f for f in files["items"]}
    assert all(f["status"] == "ready" for f in by_name.values())
    assert by_name["original.txt"]["is_duplicate"] is False
    assert by_name["renamed copy.txt"]["is_duplicate"] is True
    assert by_name["different.txt"]["duplicate_group_id"] is None

    groups = client.get(f"{API}/duplicates/groups", headers=auth_headers).json()
    assert groups["total"] == 1
    g = groups["items"][0]
    assert g["original"]["original_filename"] == "original.txt"
    assert [d["original_filename"] for d in g["duplicates"]] == ["renamed copy.txt"]
    assert g["file_size"] == 2048 and g["storage_consumed"] == 4096 and g["potential_savings"] == 2048

    s = client.get(f"{API}/analytics/summary", headers=auth_headers).json()
    assert s["total_files"] == 3
    assert s["total_storage"] == 2048 * 2 + 100
    assert s["duplicate_files"] == 1
    assert s["duplicate_storage"] == 4096
    assert s["potential_savings"] == 2048
    assert s["duplicate_groups"] == 1
    assert len(s["uploads_by_day"]) == 14 and sum(d["count"] for d in s["uploads_by_day"]) == 3
    assert s["largest_files"][0]["size_bytes"] == 2048


def test_search_filter_sort_and_pagination(client, auth_headers):
    upload(client, auth_headers, "alpha.txt", b"1" * 10)
    upload(client, auth_headers, "beta.txt", b"2" * 5000)
    upload(client, auth_headers, "gamma.csv", b"3" * 200)
    upload(client, auth_headers, "gamma_copy.csv", b"3" * 200)

    def names(**params):
        r = client.get(f"{API}/files", headers=auth_headers, params=params)
        assert r.status_code == 200, r.text
        return [f["original_filename"] for f in r.json()["items"]]

    assert names(q="alp") == ["alpha.txt"]
    assert names(q="%") == []  # wildcard characters are escaped
    assert sorted(names(q="gamma")) == ["gamma.csv", "gamma_copy.csv"]
    assert names(min_size=1000) == ["beta.txt"]
    assert sorted(names(max_size=10)) == ["alpha.txt"]
    assert names(duplicate_status="duplicate") == ["gamma_copy.csv"]
    assert names(duplicate_status="original") == ["gamma.csv"]
    assert sorted(names(duplicate_status="unique")) == ["alpha.txt", "beta.txt"]
    assert names(sort_by="size", sort_order="desc")[0] == "beta.txt"
    assert names(sort_by="name", sort_order="asc")[0] == "alpha.txt"
    assert sorted(names(file_type="document")) == sorted(["alpha.txt", "beta.txt", "gamma.csv", "gamma_copy.csv"])
    assert names(file_type="image") == []
    assert names(date_from="2000-01-01", date_to="2999-12-31", page_size=2).__len__() == 2
    assert names(date_to="2000-01-01") == []

    page2 = client.get(f"{API}/files", headers=auth_headers, params={"page": 2, "page_size": 3}).json()
    assert page2["total"] == 4 and page2["pages"] == 2 and len(page2["items"]) == 1

    assert client.get(f"{API}/files", headers=auth_headers, params={"file_type": "bogus"}).status_code == 400
    assert client.get(f"{API}/files", headers=auth_headers, params={"min_size": 10, "max_size": 1}).status_code == 400


def test_download_returns_original_bytes(client, auth_headers):
    fid = upload(client, auth_headers, "data.txt", b"download me").json()["id"]
    r = client.get(f"{API}/files/{fid}/download", headers=auth_headers)
    assert r.status_code == 200 and r.content == b"download me"
    assert "data.txt" in r.headers["content-disposition"]


def test_users_cannot_access_each_others_files(client, auth_headers, other_headers):
    fid = upload(client, auth_headers, "private.txt", b"secret").json()["id"]
    assert client.get(f"{API}/files/{fid}", headers=other_headers).status_code == 404
    assert client.get(f"{API}/files/{fid}/download", headers=other_headers).status_code == 404
    assert client.delete(f"{API}/files/{fid}?confirm=true", headers=other_headers).status_code == 404
    assert client.get(f"{API}/files", headers=other_headers).json()["total"] == 0


def test_safe_delete_flow(client, auth_headers):
    upload(client, auth_headers, "keep.txt", b"Z" * 500)
    dup_id = upload(client, auth_headers, "dup.txt", b"Z" * 500).json()["id"]

    preview = client.get(f"{API}/files/{dup_id}/delete-preview", headers=auth_headers).json()
    assert preview["storage_freed"] == 500 and preview["is_duplicate"] is True
    assert preview["copies_remaining"] == 1 and preview["can_delete"] is True

    assert client.delete(f"{API}/files/{dup_id}", headers=auth_headers).status_code == 400  # no confirmation

    assert client.patch(f"{API}/files/{dup_id}/protect", headers=auth_headers, json={"is_protected": True}).status_code == 200
    blocked = client.delete(f"{API}/files/{dup_id}?confirm=true", headers=auth_headers)
    assert blocked.status_code == 403
    assert client.get(f"{API}/files/{dup_id}/delete-preview", headers=auth_headers).json()["can_delete"] is False

    client.patch(f"{API}/files/{dup_id}/protect", headers=auth_headers, json={"is_protected": False})
    done = client.delete(f"{API}/files/{dup_id}?confirm=true&reason=cleanup", headers=auth_headers)
    assert done.status_code == 200 and done.json()["storage_freed"] == 500

    history = client.get(f"{API}/history/deletions", headers=auth_headers).json()
    assert history["total"] == 1 and history["items"][0]["filename"] == "dup.txt"
    assert history["items"][0]["reason"] == "cleanup"
    assert client.get(f"{API}/duplicates/groups", headers=auth_headers).json()["total"] == 0

    audit = client.get(f"{API}/history/audit", headers=auth_headers).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"file.upload", "file.delete", "file.protect", "user.login"} <= actions


def test_group_cleanup_keeps_original_and_protected(client, auth_headers):
    upload(client, auth_headers, "orig.txt", b"Q" * 100)
    c1 = upload(client, auth_headers, "c1.txt", b"Q" * 100).json()["id"]
    upload(client, auth_headers, "c2.txt", b"Q" * 100)
    client.patch(f"{API}/files/{c1}/protect", headers=auth_headers, json={"is_protected": True})
    gid = client.get(f"{API}/duplicates/groups", headers=auth_headers).json()["items"][0]["id"]

    assert client.post(f"{API}/duplicates/groups/{gid}/cleanup", headers=auth_headers, json={}).status_code == 400
    r = client.post(f"{API}/duplicates/groups/{gid}/cleanup", headers=auth_headers, json={"confirm": True})
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 1 and r.json()["skipped_protected"] == [c1]

    remaining = sorted(f["original_filename"] for f in client.get(f"{API}/files", headers=auth_headers).json()["items"])
    assert remaining == ["c1.txt", "orig.txt"]


def test_upload_validation(client, auth_headers):
    assert upload(client, auth_headers, "empty.txt", b"").status_code == 400
    assert upload(client, auth_headers, "virus.exe", b"data").status_code == 400
    assert upload(client, auth_headers, "fake.png", b"not a png").status_code == 400
    too_big = upload(client, auth_headers, "big.bin", b"0" * (5 * 1024 * 1024 + 1))
    assert too_big.status_code == 413
    traversal = upload(client, auth_headers, "../../evil.txt", b"hello")
    assert traversal.status_code == 201 and traversal.json()["original_filename"] == "evil.txt"


def test_file_detail_includes_metadata_and_group(client, auth_headers):
    upload(client, auth_headers, "a.txt", b"detail")
    fid = upload(client, auth_headers, "b.txt", b"detail").json()["id"]
    d = client.get(f"{API}/files/{fid}", headers=auth_headers).json()
    assert d["file_metadata"]["extension"] == "txt"
    assert d["group"]["file_count"] == 2 and d["group"]["original_filename"] == "a.txt"
    assert len(d["sha256"]) == 64


def test_health_and_rescan(client, auth_headers):
    assert client.get("/health").json()["status"] == "ok"
    upload(client, auth_headers, "a.txt", b"scan")
    upload(client, auth_headers, "b.txt", b"scan")
    r = client.post(f"{API}/duplicates/rescan", headers=auth_headers)
    assert r.status_code == 200 and r.json()["queued"] is True
    assert client.get(f"{API}/duplicates/groups", headers=auth_headers).json()["total"] == 1
