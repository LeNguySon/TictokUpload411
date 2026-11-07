"""
Profile/proxy secrets are DPAPI-protected at rest: every write path stores ``dpapi:v1:`` values and every read
through the app's connection returns plaintext, so the ~30 readers of cookies/passwords stay unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.credentials.field_crypto import is_protected
from src.infrastructure.database.connection import db_session, get_db_connection
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

COOKIE = "sessionid=fake_sess_123; msToken=fake_tok"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "secret.db"
    run_all_migrations(path)
    return path


def _raw(db: Path, sql: str, *params):
    """Reads the bytes on disk, bypassing the app's decrypting row factory."""
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, params).fetchone()
    finally:
        con.close()


def test_profile_create_and_update_store_protected_values(db: Path) -> None:
    repo = ProfileRepository(db)
    pid = repo.create({"name": "acc", "cookie": COOKIE, "password": "pw_fake_1", "totp_secret": "JBSWY3DP"})
    raw_cookie, raw_pw, raw_totp = _raw(db, "SELECT cookies_json, password, totp_secret FROM profiles WHERE id=?", pid)
    assert is_protected(raw_cookie) and is_protected(raw_pw) and is_protected(raw_totp)
    assert "sessionid" not in raw_cookie

    repo.update(pid, cookies_browser="sessionid=browser_fake", email_backup_password="mail_fake")
    repo.bulk_update_fields([pid], {"refresh_token": "rt_fake"})
    row = _raw(db, "SELECT cookies_browser, email_backup_password, refresh_token FROM profiles WHERE id=?", pid)
    assert all(is_protected(v) for v in row)


def test_reads_through_the_app_connection_are_plaintext(db: Path) -> None:
    repo = ProfileRepository(db)
    pid = repo.create({"name": "acc", "cookie": COOKIE, "password": "pw_fake_1"})
    profile = repo.get_by_id(pid)
    assert profile["cookies_json"] == COOKIE and profile["password"] == "pw_fake_1"

    with db_session(db, write=False) as conn:  # raw SQL readers (services, sniffer, workers)
        row = conn.execute("SELECT cookies_json, password FROM profiles WHERE id=?", (pid,)).fetchone()
    assert row["cookies_json"] == COOKIE and row[1] == "pw_fake_1"
    assert dict(row) == {"cookies_json": COOKIE, "password": "pw_fake_1"}


def test_queries_without_secret_columns_keep_native_rows(db: Path) -> None:
    ProfileRepository(db).create({"name": "acc"})
    conn = get_db_connection(db)
    try:
        row = conn.execute("SELECT id, name FROM profiles").fetchone()
        count = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    finally:
        conn.close()
    assert isinstance(row, sqlite3.Row) and row["name"] == "acc" and count == 1


def test_proxy_passwords_are_protected_on_every_write_path(db: Path) -> None:
    repo = ProxyRepository(db)
    a = repo.create(host="10.0.0.1", port=8080, username="u1", password="pw_a")
    b = repo.import_line("10.0.0.2:8081:u2:pw_b")
    repo.bulk_import(["10.0.0.3:8082:u3:pw_c"])
    repo.update(a, password="pw_a2")
    raws = [r[0] for r in sqlite3.connect(db).execute("SELECT password FROM proxies ORDER BY id")]
    assert len(raws) == 3 and all(is_protected(v) for v in raws)
    assert {p["password"] for p in repo.list_all()} == {"pw_a2", "pw_b", "pw_c"}
    assert repo.get_by_id(b)["password"] == "pw_b"


def test_dynamic_profile_writers_protect_secrets(db: Path) -> None:
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    pid = ProfileRepository(db).create({"name": "acc"})
    TikTokNetworkSniffer(db_path=db)._update_profile_row(pid, {"cookies_browser": "sessionid=sniffed_fake"})
    (raw,) = _raw(db, "SELECT cookies_browser FROM profiles WHERE id=?", pid)
    assert is_protected(raw)
