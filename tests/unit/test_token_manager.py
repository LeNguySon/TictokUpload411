"""P0: automatic OAuth token refresh for the official TikTok API (2026-11-07).

- Refresh 5 minutes before expiry (or when the expiry is unknown and a refresh token exists), using
  the expires_in TikTok returns; the rotated refresh token is stored in the Vault BEFORE use.
- One refresh at a time per profile (a second concurrent refresh would use an already-rotated token).
- invalid_grant => the profile must reconnect (flagged, clear error); nothing overwritten.
- Client credentials: the app-wide pair from "Cấu Hình API" (legacy format stored the client key in
  "access_token"), or the profile's own client_id when it has a matching secret.
- refresh_token / client_id imported in bulk sat in plaintext DB columns: moved to the Vault.
- A 401 from the API forces one refresh and one retry.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest
from sammonny.platforms.tiktok import TokenRefreshError, TokenSet
from src.application.services.token_manager import (
    GLOBAL_API_KEY,
    ApiConfigError,
    ReconnectRequired,
    TokenManager,
)
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository

NOW = 1_800_000_000.0


class FakeVault:
    def __init__(self, data=None, fail_save=False):
        self.data = {str(k): dict(v) for k, v in (data or {}).items()}
        self.saves: list[tuple[str, dict]] = []
        self.fail_save = fail_save

    def get_oauth_tokens(self, profile_id):
        value = self.data.get(str(profile_id))
        return dict(value) if value else None

    def save_oauth_payload(self, profile_id, payload):
        if self.fail_save:
            return False
        self.data[str(profile_id)] = dict(payload)
        self.saves.append((str(profile_id), dict(payload)))
        return True


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "t.db"
    run_all_migrations(db)
    return ProfileRepository(db)


def _manager(repo, vault, client=None, now=NOW, egress=lambda pid: "http://proxy.test:8080"):
    client = client or MagicMock()
    if not isinstance(client.refresh_access_token.side_effect, Exception) and not client.refresh_access_token.side_effect:
        client.refresh_access_token.return_value = TokenSet(
            access_token="act.new", refresh_token="rft.rotated", expires_in=7200, refresh_expires_in=15552000,
            open_id="oid", scope="video.publish")
    return TokenManager(vault=vault, profile_repo=repo, client=client, egress=egress, clock=lambda: now), client


def _vault(pid, **tokens):
    return FakeVault({
        GLOBAL_API_KEY: {"client_key": "ck", "client_secret": "cs"},
        pid: {"access_token": "act.old", "refresh_token": "rft.old", **tokens},
    })


def test_fresh_token_is_used_as_is(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-1"})
    mgr, client = _manager(repo, _vault(pid, expires_at=NOW + 3600))
    assert mgr.get_valid_access_token(pid) == "act.old"
    client.refresh_access_token.assert_not_called()


def test_expiring_token_is_refreshed_and_stored_before_use(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-2"})
    vault = _vault(pid, expires_at=NOW + 120)  # < 5 minutes left
    mgr, client = _manager(repo, vault)
    assert mgr.get_valid_access_token(pid) == "act.new"
    client.refresh_access_token.assert_called_once_with("ck", "cs", "rft.old", proxy_url="http://proxy.test:8080")
    stored = vault.data[str(pid)]
    assert stored["refresh_token"] == "rft.rotated" and stored["access_token"] == "act.new"
    assert stored["expires_at"] == NOW + 7200 and stored["refresh_expires_at"] == NOW + 15552000


def test_unknown_expiry_with_refresh_token_is_refreshed(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-3"})
    mgr, client = _manager(repo, _vault(pid))
    assert mgr.get_valid_access_token(pid) == "act.new"


def test_token_without_refresh_token_is_returned_until_it_expires(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-4"})
    vault = FakeVault({GLOBAL_API_KEY: {"client_key": "ck", "client_secret": "cs"},
                       pid: {"access_token": "pasted"}})
    mgr, client = _manager(repo, vault)
    assert mgr.get_valid_access_token(pid) == "pasted"
    vault.data[str(pid)]["expires_at"] = NOW - 1
    with pytest.raises(ReconnectRequired):
        mgr.get_valid_access_token(pid)
    client.refresh_access_token.assert_not_called()


def test_concurrent_requests_refresh_only_once(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-5"})
    vault = _vault(pid, expires_at=NOW + 10)
    client = MagicMock()
    started = threading.Event()

    def slow_refresh(*_a, **_k):
        started.set()
        time.sleep(0.2)
        return TokenSet(access_token="act.new", refresh_token="rft.rotated", expires_in=7200)

    client.refresh_access_token.side_effect = slow_refresh
    mgr, _ = _manager(repo, vault, client=client)
    results = []
    threads = [threading.Thread(target=lambda: results.append(mgr.get_valid_access_token(pid))) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["act.new"] * 3 and client.refresh_access_token.call_count == 1


def test_invalid_grant_flags_the_profile_and_keeps_stored_tokens(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-6"})
    vault = _vault(pid, expires_at=NOW - 5)
    client = MagicMock()
    client.refresh_access_token.side_effect = TokenRefreshError("invalid_grant", reconnect_required=True)
    mgr, _ = _manager(repo, vault, client=client)
    with pytest.raises(ReconnectRequired):
        mgr.get_valid_access_token(pid)
    assert repo.get_by_id(pid)["api_reconnect_required"] == 1
    assert vault.data[str(pid)]["refresh_token"] == "rft.old" and not vault.saves


def test_vault_write_failure_never_returns_an_unsaved_token(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-7"})
    vault = _vault(pid, expires_at=NOW + 10)
    vault.fail_save = True
    mgr, _ = _manager(repo, vault)
    with pytest.raises(RuntimeError, match="Vault"):
        mgr.get_valid_access_token(pid)


def test_plaintext_refresh_token_moves_from_the_database_to_the_vault(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-8", "refresh_token": "rft.db", "client_id": "ck"})
    vault = FakeVault({GLOBAL_API_KEY: {"client_key": "ck", "client_secret": "cs"}})
    mgr, client = _manager(repo, vault)
    assert mgr.get_valid_access_token(pid) == "act.new"
    assert client.refresh_access_token.call_args.args[2] == "rft.db"
    assert repo.get_by_id(pid)["refresh_token"] is None  # no plaintext secret left
    assert vault.data[str(pid)]["refresh_token"] == "rft.rotated"


def test_legacy_global_config_format_is_understood(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-9"})
    vault = FakeVault({GLOBAL_API_KEY: {"access_token": "ck-legacy", "client_secret": "cs"},
                       pid: {"access_token": "a", "refresh_token": "r", "expires_at": NOW}})
    mgr, client = _manager(repo, vault)
    mgr.get_valid_access_token(pid)
    assert client.refresh_access_token.call_args.args[:2] == ("ck-legacy", "cs")


def test_profile_client_id_without_its_secret_is_a_config_error(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-10", "client_id": "other-app"})
    mgr, client = _manager(repo, _vault(pid, expires_at=NOW))
    with pytest.raises(ApiConfigError):
        mgr.get_valid_access_token(pid)
    client.refresh_access_token.assert_not_called()


def test_refresh_goes_through_the_profile_egress(repo):
    from src.infrastructure.proxy.egress import EgressBlocked

    pid = repo.create({"name": "A", "uuid": "uuid-tok-11"})

    def blocked(_pid):
        raise EgressBlocked("no proxy")

    mgr, client = _manager(repo, _vault(pid, expires_at=NOW), egress=blocked)
    with pytest.raises(EgressBlocked):
        mgr.get_valid_access_token(pid)
    client.refresh_access_token.assert_not_called()


# ------------------------------------------------------------------ adapter integration
def test_adapter_uses_refreshed_token_and_retries_once_on_401(tmp_path):
    from sammonny import UploadResult
    from src.application.settings.upload_settings import UploadMethod, UploadSettings
    from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

    tokens = MagicMock()
    tokens.get_valid_access_token.side_effect = lambda pid, force=False: "act.forced" if force else "act.cached"
    direct = MagicMock()
    calls = []

    def creator_info(token):
        calls.append(token)
        if token == "act.cached":
            raise RuntimeError("Creator info query failed (HTTP 401): access_token_invalid")
        return {"privacy_level_options": ["SELF_ONLY"]}

    direct.query_creator_info.side_effect = creator_info
    adapter = SamMonnyTikTokAdapter(vault=MagicMock(), direct_client=direct, db_path=tmp_path / "x.db",
                                    session_factory=MagicMock(), token_manager=tokens)
    adapter._profile_egress = lambda _pid: "http://proxy.test:8080"
    adapter.apply_settings(UploadSettings(UploadMethod.OFFICIAL))
    adapter.publisher = MagicMock()
    adapter.publisher._tokens = {}
    adapter.publisher.upload.return_value = UploadResult(success=True, draft_id="d", publish_id="v_pub_1")
    adapter.publisher.reconcile.return_value = __import__("sammonny").RemoteStatus.PUBLISH_COMPLETE
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 64)
    assert adapter.upload_video(profile_id=1, video_path=video, title="t").success
    assert calls == ["act.cached", "act.forced"]
    adapter.publisher.register_access_token.assert_called_with("1", "act.forced")


def test_api_config_dialog_stores_the_client_key_in_its_own_field(qtbot):
    from src.presentation.dialogs.api_cookie_dialog import ApiCookieDialog

    vault = MagicMock()
    dlg = ApiCookieDialog(vault=vault)
    qtbot.addWidget(dlg)
    dlg.txt_client_key.setText("ck-123")
    dlg.txt_client_secret.setText("cs-456")
    dlg._on_save()
    vault.save_oauth_payload.assert_called_once_with(GLOBAL_API_KEY, {"client_key": "ck-123", "client_secret": "cs-456"})


# ------------------------------------------------------------------ UI: reconnect status
def test_profile_table_shows_api_reconnect_needed(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles([{"id": 1, "name": "A", "uuid": "u", "api_reconnect_required": 1},
                         {"id": 2, "name": "B", "uuid": "v"}])
    assert "kết nối lại" in table.item(0, 3).toolTip()
    assert "kết nối lại" not in (table.item(1, 3).toolTip() or "")


def test_editing_a_profile_token_keeps_its_refresh_token_and_clears_the_flag(qtbot, repo):
    from src.presentation.dialogs.add_profile_dialog import AddProfileDialog

    pid = repo.create({"name": "A", "uuid": "uuid-tok-12", "api_reconnect_required": 1})
    vault = FakeVault({pid: {"access_token": "old", "refresh_token": "rft.keep", "expires_at": NOW}})
    dlg = AddProfileDialog(profile_repo=repo, project_repo=MagicMock(list_all=lambda *a, **k: []),
                           proxy_repo=MagicMock(list_all=lambda *a, **k: []), vault=vault,
                           profile_data=repo.get_by_id(pid))
    qtbot.addWidget(dlg)
    dlg.token_input.setText("act.pasted")
    dlg._on_save()
    stored = vault.data[str(pid)]
    assert stored["access_token"] == "act.pasted" and stored["refresh_token"] == "rft.keep"
    assert stored.get("expires_at") is None  # unknown: refreshed on first use
    assert repo.get_by_id(pid)["api_reconnect_required"] == 0


def test_missing_client_config_uses_a_possibly_valid_token_but_not_an_expired_one(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-tok-13"})
    vault = FakeVault({pid: {"access_token": "act.cur", "refresh_token": "rft"}})  # no GLOBAL config
    mgr, client = _manager(repo, vault)
    assert mgr.get_valid_access_token(pid) == "act.cur"  # unknown expiry: still usable
    vault.data[str(pid)]["expires_at"] = NOW - 10
    with pytest.raises(ApiConfigError):
        mgr.get_valid_access_token(pid)
    client.refresh_access_token.assert_not_called()
