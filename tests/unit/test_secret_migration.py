"""Existing plaintext secrets are DPAPI-protected by the migration (idempotent, backup first)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.infrastructure.credentials.field_crypto import is_protected
from src.infrastructure.database.migrations.runner import protect_plaintext_secrets, run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


def _legacy_db(tmp_path: Path) -> Path:
    """A database written before encryption: secrets inserted as plaintext with raw SQL."""
    db = tmp_path / "legacy.db"
    run_all_migrations(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO profiles (uuid, name, storage_dir, user_agent, cookies_json, password, totp_secret)"
        " VALUES (?,?,?,?,?,?,?)",
        ("u-1", "legacy", "profiles/legacy", "UA", "sessionid=legacy_fake", "pw_legacy", ""),
    )
    con.execute("INSERT INTO proxies (host, port, username, password) VALUES ('10.0.0.9', 8080, 'u', 'px_legacy')")
    con.commit()
    con.close()
    return db


def test_migration_protects_plaintext_and_is_idempotent(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)
    counts = protect_plaintext_secrets(db, backup_dir=tmp_path / "bk")
    assert counts == {"profiles": 2, "proxies": 1}  # cookies_json + password; empty totp untouched

    con = sqlite3.connect(db)
    cookie, pw, totp = con.execute("SELECT cookies_json, password, totp_secret FROM profiles").fetchone()
    (px,) = con.execute("SELECT password FROM proxies").fetchone()
    con.close()
    assert is_protected(cookie) and is_protected(pw) and is_protected(px) and totp == ""

    assert protect_plaintext_secrets(db, backup_dir=tmp_path / "bk") == {"profiles": 0, "proxies": 0}
    assert ProfileRepository(db).list_all()[0]["cookies_json"] == "sessionid=legacy_fake"
    assert ProxyRepository(db).list_all()[0]["password"] == "px_legacy"


def test_migration_backs_up_once_before_changing_anything(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)
    bk = tmp_path / "bk"
    protect_plaintext_secrets(db, backup_dir=bk)
    backups = list(bk.glob("*.db"))
    assert len(backups) == 1
    (cookie,) = sqlite3.connect(backups[0]).execute("SELECT cookies_json FROM profiles").fetchone()
    assert cookie == "sessionid=legacy_fake"  # pre-migration copy
    protect_plaintext_secrets(db, backup_dir=bk)
    assert len(list(bk.glob("*.db"))) == 1  # nothing left to migrate: no new backup


def test_run_all_migrations_protects_existing_plaintext(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)
    run_all_migrations(db)
    (cookie,) = sqlite3.connect(db).execute("SELECT cookies_json FROM profiles").fetchone()
    assert is_protected(cookie)
