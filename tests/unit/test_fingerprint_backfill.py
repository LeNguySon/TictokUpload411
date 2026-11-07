"""Existing profiles without a stored fingerprint get one: the daemon's own record when it has one (the browser
already uses it), otherwise a unique one derived from the profile uuid."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.application.services.gologin_sync_service import backfill_fingerprints
from src.domain.fingerprint.browser_fingerprint import generate_fingerprint
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository

DAEMON_FP = generate_fingerprint("what-the-daemon-made")


def test_backfill_prefers_daemon_record_then_local_and_skips_existing(tmp_path: Path) -> None:
    db = tmp_path / "bf.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    ids = [repo.create({"name": n, "uuid": f"uuid-{n}"}) for n in ("daemon", "local", "kept")]
    kept_fp = json.loads(repo.get_by_id(ids[2])["fingerprint_json"])
    with db_session(db) as conn:  # simulate legacy rows (created before fingerprints were stored)
        conn.execute("UPDATE profiles SET fingerprint_json = NULL WHERE id IN (?, ?)", (ids[0], ids[1]))

    client = MagicMock()
    client.get_profile.side_effect = lambda uid: (
        MagicMock(raw_data={"fingerprint": DAEMON_FP}) if uid == "uuid-daemon" else None
    )
    counts = backfill_fingerprints(repo, client)

    assert counts == {"daemon": 1, "generated": 1}
    assert json.loads(repo.get_by_id(ids[0])["fingerprint_json"]) == DAEMON_FP
    assert repo.get_by_id(ids[0])["user_agent"] == DAEMON_FP["navigator"]["user_agent"]
    assert json.loads(repo.get_by_id(ids[1])["fingerprint_json"]) == generate_fingerprint("uuid-local")
    assert json.loads(repo.get_by_id(ids[2])["fingerprint_json"]) == kept_fp
    assert backfill_fingerprints(repo, client) == {"daemon": 0, "generated": 0}


def test_backfill_without_daemon_generates_locally(tmp_path: Path) -> None:
    db = tmp_path / "bf2.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "x", "uuid": "uuid-x"})
    with db_session(db) as conn:
        conn.execute("UPDATE profiles SET fingerprint_json = NULL WHERE id = ?", (pid,))
    assert backfill_fingerprints(repo, None) == {"daemon": 0, "generated": 1}
