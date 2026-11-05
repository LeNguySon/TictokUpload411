"""License-driven UI: footer, per-plan feature gating, activation dialog, runtime lock, lower-layer guards."""

from __future__ import annotations

import time
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PyQt6.QtWidgets import QDialog
from src.domain.licensing import entitlements
from src.domain.licensing.claims import LicenseClaims, LicenseState, LicenseStatus
from src.domain.licensing.plans import Feature
from src.infrastructure.licensing.license_store import LicenseStore
from src.infrastructure.licensing.verifier import encode_license, public_key_b64

DAY = 86400
MID = "1111-2222-3333-4444"


def _set_plan(plan: str, sub: str = "Khách A", exp: int | None = None) -> LicenseClaims:
    now = int(time.time())
    claims = LicenseClaims.from_dict(
        {"lid": "l1", "sub": sub, "plan": plan, "iat": now - DAY, "exp": exp or now + 30 * DAY, "mid": MID},
        kid="k1",
    )
    entitlements.set_current(claims)
    return claims


@pytest.fixture
def make_window(qtbot, tmp_path):
    from src.infrastructure.database.migrations.runner import run_all_migrations

    db = tmp_path / "lic.db"
    run_all_migrations(db)
    created = []

    def make(license_service=None):
        with (
            patch("src.presentation.views.main_window.MetricsSyncWorker"),
            patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        ):
            from src.presentation.views.main_window import TikTokManagerMainWindow

            win = TikTokManagerMainWindow(db_path=db, license_service=license_service)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        qtbot.addWidget(win)
        created.append(win)
        return win

    return make


def test_version_matches_pyproject():
    from src.version import __version__

    assert __version__ == tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_footer_shows_real_license(make_window):
    from src.version import __version__

    claims = _set_plan("pro", sub="Nguyễn Văn B")
    text = make_window().lbl_footer_status.text()
    assert "Nguyễn Văn B" in text and "Gói 3" in text and __version__ in text
    assert time.strftime("%d-%m-%Y", time.localtime(claims.exp)) in text
    assert "1.5.5.2" not in text and "Goepro" not in text


def test_profile_plan_disables_upload_and_channel_tools(make_window):
    _set_plan("profile")
    win = make_window()
    for btn in (win.btn_batch_upload, win.btn_pick_pc, win.btn_schedule, win.btn_start_upload):
        assert not btn.isEnabled()
        assert "Gói 2" in btn.toolTip()
    assert not win.act_radar.isEnabled() and not win.act_health.isEnabled()


def test_upload_plan_enables_upload_only(make_window):
    _set_plan("upload")
    win = make_window()
    assert win.btn_start_upload.isEnabled() and win.btn_schedule.isEnabled()
    assert not win.act_radar.isEnabled() and not win.act_health.isEnabled()


def test_pro_plan_enables_everything(make_window):
    _set_plan("pro")
    win = make_window()
    assert win.btn_start_upload.isEnabled() and win.act_radar.isEnabled() and win.act_health.isEnabled()


def test_gated_handlers_refuse_without_feature(make_window):
    _set_plan("profile")
    win = make_window()
    win.video_repo.list_scheduled_due = MagicMock(return_value=[])
    win.thread_pool.dispatch_upload = MagicMock()
    with patch("src.presentation.views.main_window.InfoBar") as info:
        win._on_start_upload_queue()
        win._on_add_video_for_profiles([1])
        win._on_open_channel_radar(1)
        win._on_open_account_health(1)
    assert info.warning.call_count == 4
    win._check_scheduled_queue()  # automatic upload is silently skipped
    win.video_repo.list_scheduled_due.assert_not_called()
    win.thread_pool.dispatch_upload.assert_not_called()


def test_upload_worker_refuses_without_upload_plan():
    from src.application.workers.upload_worker import UploadWorker

    _set_plan("profile")
    service = MagicMock()
    bus = MagicMock()
    UploadWorker(video_id=1, profile_id=2, upload_service=service, signal_bus=bus).execute()
    service.execute_upload.assert_not_called()
    bus.upload_failed.emit.assert_called_once()


def test_moderation_service_requires_pro(tmp_path):
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    _set_plan("upload")
    svc = TikTokModerationService(db_path=tmp_path / "x.db")
    for call in (
        lambda: svc.fetch_account_standing(1),
        lambda: svc.fetch_video_violations(1),
        lambda: svc.check_appeal_status(1),
    ):
        with pytest.raises(entitlements.LicenseFeatureError):
            call()


def test_expired_while_running_locks_and_quits_when_not_reactivated(make_window):
    _set_plan("pro")
    svc = MagicMock()
    svc.runtime_check.return_value = LicenseState(LicenseStatus.EXPIRED)
    win = make_window(license_service=svc)
    win.show()
    with (
        patch("src.presentation.views.main_window.LicenseActivationDialog") as dlg_cls,
        patch("src.presentation.views.main_window.QApplication.quit") as quit_app,
    ):
        dlg_cls.return_value.exec.return_value = QDialog.DialogCode.Rejected
        win._check_license()
    assert not win.isVisible()
    quit_app.assert_called_once()


def test_expired_while_running_reactivated_shows_again(make_window):
    _set_plan("pro")
    svc = MagicMock()
    svc.runtime_check.return_value = LicenseState(LicenseStatus.EXPIRED)
    win = make_window(license_service=svc)
    win.show()
    with patch("src.presentation.views.main_window.LicenseActivationDialog") as dlg_cls:
        dlg_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
        _set_plan("upload", sub="Gia hạn")
        win._check_license()
    assert win.isVisible() and "Gia hạn" in win.lbl_footer_status.text()


def test_activation_dialog(qtbot, tmp_path):
    from src.application.services.license_service import LicenseService
    from src.presentation.dialogs.license_activation_dialog import LicenseActivationDialog

    sk = Ed25519PrivateKey.generate()
    svc = LicenseService(
        store=LicenseStore(tmp_path / "l.dat"), trusted={"k1": public_key_b64(sk)}, revoked=(),
        machine_code_fn=lambda: MID,
    )
    dlg = LicenseActivationDialog(svc, LicenseState(LicenseStatus.MISSING))
    qtbot.addWidget(dlg)
    assert dlg.txt_machine_code.text() == MID and dlg.txt_machine_code.isReadOnly()
    assert "chưa được kích hoạt" in dlg.lbl_status.text()

    dlg.txt_key.setPlainText("TAVM1.rác.rác")
    dlg._on_activate()
    assert dlg.result() != QDialog.DialogCode.Accepted and "định dạng" in dlg.lbl_status.text()

    now = int(time.time())
    good = encode_license(
        {"lid": "l9", "sub": "C", "plan": "pro", "iat": now - 60, "exp": now + DAY, "mid": MID}, sk, kid="k1"
    )
    dlg.txt_key.setPlainText(good)
    dlg._on_activate()
    assert dlg.result() == QDialog.DialogCode.Accepted and entitlements.has(Feature.CHANNEL_HEALTH)
