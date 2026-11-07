"""Upload methods (official API / cookie hybrid / Studio DOM) and the user's upload settings.

Defects reproduced (audit 2026-11-06):
- The SDK always uses the official API when a token exists (preferred mode ignored) and silently
  switches to a browser upload when the API check fails.
- "Schedule on TikTok" with the official API or DOM posted immediately (they ignore schedule_time).
- DOM ignores privacy (a "SELF_ONLY" video went public) and the SDK's hybrid -> DOM fallback can
  repost after an ambiguous hybrid publish.
- DOM reported success with a synthetic id even when nothing was confirmed.
- Official uploads were marked published while TikTok was still processing (never reconciled),
  and privacy was not checked against what the account may use.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QSettings
from sammonny import RemoteStatus, UploadMode, UploadResult
from src.application.settings.upload_settings import (
    UploadMethod,
    UploadSettings,
    load_upload_settings,
    save_upload_settings,
)
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.tiktok.sammonny_adapter import (
    DomUploadBlocked,
    LazyActiveSession,
    SamMonnyTikTokAdapter,
    UploadMethodError,
)

FUTURE = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ settings
def test_settings_defaults_and_roundtrip(tmp_path):
    store = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    defaults = load_upload_settings(store)
    assert defaults == UploadSettings(UploadMethod.AUTO, allow_fallback=False, studio_show_browser=False,
                                      reconcile_official=True)
    custom = UploadSettings(UploadMethod.STUDIO, allow_fallback=True, studio_show_browser=True, reconcile_official=False)
    save_upload_settings(custom, store)
    assert load_upload_settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)) == custom


def test_unknown_stored_method_falls_back_to_auto(tmp_path):
    store = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    store.setValue("upload/method", "carrier-pigeon")
    assert load_upload_settings(store).method is UploadMethod.AUTO


# ------------------------------------------------------------------ adapter harness
def _adapter(tmp_path, method=UploadMethod.AUTO, token="tok", allow_fallback=False, creator_info=None,
             creator_error=None, result=None, reconcile=None):
    vault = MagicMock()
    vault.get_oauth_tokens.return_value = {"access_token": token} if token else None
    direct = MagicMock()
    if creator_error:
        direct.query_creator_info.side_effect = creator_error
    else:
        direct.query_creator_info.return_value = creator_info or {
            "privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}
    adapter = SamMonnyTikTokAdapter(vault=vault, direct_client=direct, db_path=tmp_path / "x.db",
                                    session_factory=MagicMock())
    adapter._profile_egress = lambda _pid: "http://proxy.test:8080"
    adapter.apply_settings(UploadSettings(method, allow_fallback=allow_fallback, studio_show_browser=False,
                                          reconcile_official=True))
    adapter.reconcile_poll_s = 0
    adapter.publisher = MagicMock()
    adapter.publisher._tokens = {}
    adapter.publisher.upload.return_value = result or UploadResult(success=True, draft_id="d", publish_id="7400000000000000001")
    adapter.publisher.reconcile.return_value = reconcile or RemoteStatus.PUBLISH_COMPLETE
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 64)
    return adapter, video


def _mode(adapter):
    return adapter.publisher.upload.call_args.kwargs["preferred_mode"]


# ------------------------------------------------------------------ chosen method is honoured
def test_official_without_token_is_refused(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, token=None)
    with pytest.raises(UploadMethodError, match="OAuth"):
        adapter.upload_video(profile_id=1, video_path=video, title="t")
    adapter.publisher.upload.assert_not_called()


def test_official_api_failure_is_reported_not_silently_switched(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, creator_error=RuntimeError("token revoked"))
    with pytest.raises(UploadMethodError, match="token revoked"):
        adapter.upload_video(profile_id=1, video_path=video, title="t")
    adapter.publisher.upload.assert_not_called()


def test_official_api_failure_with_fallback_allowed_uses_studio_for_public_videos(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, allow_fallback=True,
                              creator_error=RuntimeError("token revoked"))
    adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert _mode(adapter) is UploadMode.HEADLESS_STUDIO  # Cookie Hybrid does not upload real data
    assert "1" not in adapter.publisher._tokens  # the SDK would otherwise force the API again


def test_official_api_failure_cannot_fall_back_for_a_private_video(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, allow_fallback=True,
                              creator_error=RuntimeError("token revoked"))
    with pytest.raises(UploadMethodError, match="token revoked"):
        adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="SELF_ONLY")
    adapter.publisher.upload.assert_not_called()


@pytest.mark.parametrize(("method", "mode"), [(UploadMethod.STUDIO, UploadMode.HEADLESS_STUDIO)])
def test_forced_browser_methods_ignore_an_existing_token(tmp_path, method, mode):
    adapter, video = _adapter(tmp_path, method)
    adapter.publisher._tokens["1"] = "stale"
    adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert _mode(adapter) is mode and "1" not in adapter.publisher._tokens


def test_chosen_cookie_hybrid_routes_to_hybrid_uploader(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.HYBRID, token=None)
    adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert _mode(adapter) is UploadMode.COOKIE_API_HYBRID


def test_auto_uses_official_with_token_and_studio_without(tmp_path):
    adapter, video = _adapter(tmp_path)
    adapter.upload_video(profile_id=1, video_path=video, title="t")
    assert _mode(adapter) is UploadMode.OFFICIAL_DIRECT_POST
    (tmp_path / "b").mkdir()
    adapter2, video2 = _adapter(tmp_path / "b", token=None)
    adapter2.upload_video(profile_id=1, video_path=video2, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert _mode(adapter2) is UploadMode.HEADLESS_STUDIO


@pytest.mark.parametrize(("privacy", "schedule"), [("SELF_ONLY", None), ("PUBLIC_TO_EVERYONE", FUTURE)])
def test_auto_without_token_needs_the_api_for_private_or_scheduled_videos(tmp_path, privacy, schedule):
    adapter, video = _adapter(tmp_path, token=None)
    with pytest.raises(UploadMethodError, match="TikTok API"):
        adapter.upload_video(profile_id=1, video_path=video, title="t", privacy=privacy, schedule_time=schedule)
    adapter.publisher.upload.assert_not_called()


def test_official_privacy_must_be_allowed_for_the_account(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, creator_info={"privacy_level_options": ["SELF_ONLY"]})
    with pytest.raises(UploadMethodError, match="PUBLIC_TO_EVERYONE"):
        adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    adapter.publisher.upload.assert_not_called()


# ------------------------------------------------------------------ native scheduling support
@pytest.mark.parametrize(
    ("method", "token", "native"),
    [(UploadMethod.OFFICIAL, "tok", False), (UploadMethod.STUDIO, "tok", False), (UploadMethod.HYBRID, None, True),
     (UploadMethod.AUTO, "tok", False), (UploadMethod.AUTO, None, False)],
)
def test_supports_native_schedule(tmp_path, method, token, native):
    adapter, _ = _adapter(tmp_path, method, token=token)
    assert adapter.supports_native_schedule(1) is native


def test_scheduled_video_is_kept_for_the_app_scheduler_when_tiktok_cannot_hold_it(tmp_path):
    from src.application.services.upload_service import UploadService
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
    from src.infrastructure.database.repositories.video_repository import VideoRepository

    db = tmp_path / "u.db"
    run_all_migrations(db)
    profiles, videos = ProfileRepository(db), VideoRepository(db)
    pid = profiles.create({"name": "U", "uuid": "uuid-sched-1", "status": "LIVE"})
    profiles.update(pid, proxy_id=ProxyRepository(db).create(host="10.0.0.10", port=8080))
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x" * 100)
    vid = videos.register_or_update(video_hash="h1", file_path=str(f), file_name="caption", file_size=100,
                                    mtime=f.stat().st_mtime, schedule_time=FUTURE, assigned_profile_id=pid)
    adapter = MagicMock()
    adapter.supports_native_schedule.return_value = False
    result = UploadService(profile_repo=profiles, video_repo=videos, tiktok_adapter=adapter).execute_upload(
        video_id=vid, profile_id=pid, schedule_time=FUTURE)
    adapter.upload_video.assert_not_called()  # nothing is posted now
    row = videos.get_by_id(vid)
    assert row["status"] == "available" and row["schedule_time"] == FUTURE and row["assigned_profile_id"] == pid
    assert result.status is RemoteStatus.PENDING and not result.success and not result.error


# ------------------------------------------------------------------ DOM guards
def test_dom_upload_of_a_non_public_video_is_refused(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.STUDIO)
    with pytest.raises(UploadMethodError, match="riêng tư"):
        adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="SELF_ONLY")
    adapter.publisher.upload.assert_not_called()


@pytest.mark.parametrize(
    ("method", "privacy", "schedule", "allow_fallback", "dom_allowed"),
    [
        (UploadMethod.STUDIO, "PUBLIC_TO_EVERYONE", None, False, True),
        (UploadMethod.AUTO, "PUBLIC_TO_EVERYONE", None, False, True),  # no token: Studio
    ],
)
def test_dom_permission_per_upload(tmp_path, method, privacy, schedule, allow_fallback, dom_allowed):
    adapter, video = _adapter(tmp_path, method, token=None, allow_fallback=allow_fallback)
    seen = {}
    adapter.publisher.upload.side_effect = lambda **kw: seen.update(adapter._upload_context()) or UploadResult(
        success=True, draft_id="d", publish_id="1")
    adapter.upload_video(profile_id=1, video_path=video, title="t", privacy=privacy, schedule_time=schedule)
    assert seen["dom_allowed"] is dom_allowed


def test_guarded_session_blocks_dom_file_attach():
    raw = MagicMock()
    raw._cdp = object()
    session = LazyActiveSession(raw, dom_upload_allowed=False, dom_block_reason="không cho phép")
    session.cdp.send("Runtime.evaluate", {"expression": "1"})  # hybrid signing still works
    with pytest.raises(DomUploadBlocked, match="không cho phép"):
        session.cdp.send("DOM.setFileInputFiles", {"files": ["v.mp4"]})
    raw.cdp.send.assert_called_once()


def test_unconfirmed_dom_result_is_not_reported_as_published(tmp_path):
    unconfirmed = UploadResult(success=True, draft_id="d", publish_id="studio_post_1762400000",
                               status=RemoteStatus.PUBLISH_COMPLETE)
    adapter, video = _adapter(tmp_path, UploadMethod.STUDIO, token=None, result=unconfirmed)
    res = adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert not res.success and res.is_ambiguous and "TikTok Studio" in res.error


# ------------------------------------------------------------------ official reconciliation
def test_official_result_is_reconciled_until_tiktok_finishes(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL, reconcile=RemoteStatus.FAILED,
                              result=UploadResult(success=True, draft_id="d", publish_id="v_pub_123456789012",
                                                  status=RemoteStatus.PROCESSING_UPLOAD))
    res = adapter.upload_video(profile_id=1, video_path=video, title="t")
    assert not res.success and "TikTok" in res.error
    adapter.publisher.reconcile.assert_called_with("v_pub_123456789012", account_id="1")


def test_official_result_published_after_reconcile(tmp_path):
    adapter, video = _adapter(tmp_path, UploadMethod.OFFICIAL,
                              result=UploadResult(success=True, draft_id="d", publish_id="v_pub_123456789012",
                                                  status=RemoteStatus.PROCESSING_UPLOAD))
    res = adapter.upload_video(profile_id=1, video_path=video, title="t")
    assert res.success and res.status is RemoteStatus.PUBLISH_COMPLETE


# ------------------------------------------------------------------ settings dialog / window
def test_settings_dialog_saves_and_applies(qtbot, tmp_path):
    from src.presentation.dialogs.upload_settings_dialog import UploadSettingsDialog

    store = QSettings(str(tmp_path / "d.ini"), QSettings.Format.IniFormat)
    applied = []
    dlg = UploadSettingsDialog(store=store, on_saved=applied.append)
    qtbot.addWidget(dlg)
    dlg.cmb_method.setCurrentIndex(dlg.cmb_method.findData(UploadMethod.STUDIO.value))
    dlg.sw_fallback.setChecked(True)
    dlg.sw_show_browser.setChecked(True)
    dlg._on_save()
    assert drain_ui_tasks(timeout_s=15)  # new profiles are created off the GUI thread
    saved = load_upload_settings(store)
    assert saved.method is UploadMethod.STUDIO and saved.allow_fallback and saved.studio_show_browser
    assert applied == [saved]


def test_window_applies_saved_settings_and_has_menu_entry(qtbot, tmp_path):
    from unittest.mock import patch

    from src.infrastructure.database.migrations.runner import run_all_migrations

    db = tmp_path / "mw.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        save_upload_settings(UploadSettings(UploadMethod.HYBRID, True, False, True), TikTokManagerMainWindow._settings(None))
        win = TikTokManagerMainWindow(db_path=db)
    qtbot.addWidget(win)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    assert win.tiktok_adapter.settings.method is UploadMethod.HYBRID
    assert hasattr(win, "act_upload_settings")
    assert Path  # keep import used
