"""
Backup bundles (Nhận và Gửi) carry cookies/passwords, and DPAPI values cannot move to another machine, so the
export is encrypted with a user passphrase (scrypt -> AES-256-GCM). Legacy plaintext bundles still import.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from src.infrastructure.credentials import backup_crypto as bc
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs import sync_transfer_dialog as st

COOKIE = "sessionid=bundle_fake_1; msToken=fake"


def test_encrypt_decrypt_roundtrip_and_wrong_passphrase() -> None:
    blob = bc.encrypt_bundle(b'{"secret": "x"}', "correct horse battery")
    assert blob.startswith(bc.MAGIC) and b"secret" not in blob
    assert bc.decrypt_bundle(blob, "correct horse battery") == b'{"secret": "x"}'
    with pytest.raises(bc.BackupPasswordError):
        bc.decrypt_bundle(blob, "wrong passphrase")
    with pytest.raises(bc.BackupPasswordError):
        bc.decrypt_bundle(blob[:-1] + bytes([blob[-1] ^ 1]), "correct horse battery")  # tampered


def _repos(db: Path):
    run_all_migrations(db)
    return ProfileRepository(db), ProxyRepository(db), ProjectRepository(db)


def test_export_is_encrypted_and_imports_on_another_database(tmp_path: Path) -> None:
    prof, prox, proj = _repos(tmp_path / "a.db")
    prof.create({"name": "acc_bundle", "cookie": COOKIE})
    prox.create(host="10.1.1.1", port=8080, username="u", password="px_fake")
    bundle = tmp_path / "backup.zip"

    count = st.export_project_dataset(
        zip_path=bundle, project_id=None, profile_repo=prof, proxy_repo=prox, project_repo=proj,
        passphrase="pass phrase 1",
    )
    assert count == 1
    raw = b"".join(zipfile.ZipFile(bundle).read(n) for n in zipfile.ZipFile(bundle).namelist())
    assert b"bundle_fake_1" not in raw and b"px_fake" not in raw and b"acc_bundle" not in raw
    assert st.bundle_is_encrypted(bundle)

    prof2, prox2, proj2 = _repos(tmp_path / "b.db")
    with pytest.raises(bc.BackupPasswordError):
        st.import_project_dataset(bundle, prof2, prox2, proj2, passphrase="nope")
    p_count, px_count = st.import_project_dataset(bundle, prof2, prox2, proj2, passphrase="pass phrase 1")
    assert (p_count, px_count) == (1, 1)
    assert prof2.list_all()[0]["cookies_json"] == COOKIE
    assert prox2.list_all()[0]["password"] == "px_fake"


def test_export_requires_a_passphrase(tmp_path: Path) -> None:
    prof, prox, proj = _repos(tmp_path / "a.db")
    with pytest.raises(ValueError):
        st.export_project_dataset(
            zip_path=tmp_path / "x.zip", project_id=None, profile_repo=prof, proxy_repo=prox, project_repo=proj,
            passphrase="",
        )


def test_legacy_plaintext_bundle_still_imports(tmp_path: Path) -> None:
    bundle = tmp_path / "legacy.zip"
    manifest = {"version": "1.0.0", "profiles": [{"name": "old_acc", "cookies_json": COOKIE}], "proxies": [],
                "projects": []}
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("dataset_manifest.json", json.dumps(manifest))
    assert not st.bundle_is_encrypted(bundle)
    prof, prox, proj = _repos(tmp_path / "c.db")
    assert st.import_project_dataset(bundle, prof, prox, proj) == (1, 0)
    assert prof.list_all()[0]["cookies_json"] == COOKIE
