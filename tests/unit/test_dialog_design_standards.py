"""Design-standard checks applied to EVERY dialog (instinct 030 + UI audit 2026-11-05).

Each check came from a defect seen in real-platform screenshots of all dialogs:
- Fluent SpinBox/DateTimeEdit showed no value (inner line edit 1 px wide with Qt 6.12).
- "&" in titles/tabs/buttons/checkboxes was eaten as a mnemonic ("Sức Khỏe  Thống Kê").
- Header banners stretched vertically (title and subtitle far apart).
- Raw Qt widgets (QCheckBox, QPushButton, QDateTimeEdit, ...) instead of Fluent ones.
- AccountHealthDialog forced a dark navy theme inside the light app (title unreadable).
- Emoji used as icons in buttons/tabs/titles (Fluent icons are the standard).
- Option checkboxes clipped ("Cho phép Due", "AI-Generatec").
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QWidget,
)

EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐✅❌⚠⌚-⏿]")  # incl. misc-technical (⌨ ⏳)
RAW_QT = (QCheckBox, QPushButton, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QLineEdit)


@pytest.fixture(scope="module")
def dialogs(tmp_path_factory):
    app = QApplication.instance() or QApplication([])
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.project_repository import ProjectRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
    from src.infrastructure.database.repositories.video_repository import VideoRepository
    from src.presentation.dialogs import (
        account_health_dialog,
        add_profile_dialog,
        api_cookie_dialog,
        assign_project_dialog,
        assign_proxy_dialog,
        batch_channel_update_dialog,
        batch_folder_upload_dialog,
        bulk_add_profile_dialog,
        bulk_edit_profile_dialog,
        channel_radar_dialog,
        permissions_dialog,
        project_dialog,
        proxy_dialog,
        schedule_dialog,
        sync_transfer_dialog,
        table_settings_dialog,
        trash_dialog,
        user_guide_dialog,
        video_metadata_dialog,
    )

    tmp = tmp_path_factory.mktemp("dlg")
    db = tmp / "d.db"
    run_all_migrations(db)
    prof, proj, prox, vids = ProfileRepository(db), ProjectRepository(db), ProxyRepository(db), VideoRepository(db)
    p1 = proj.create(name="Kênh Nhật Bản")
    ids = [prof.create({"name": f"D{i}", "uuid": f"uuid-dlg-{i:04d}", "project_id": p1}) for i in range(1, 4)]
    vdir = tmp / "v"
    vdir.mkdir()
    (vdir / "a.mp4").write_bytes(b"x")
    vids.register_or_update(video_hash="h", file_path=str(vdir / "a.mp4"), file_name="Demo", file_size=1, mtime=1.0)
    vault = MagicMock()
    vault.get_oauth_tokens.return_value = None
    vrow = vids.list_available(only_available=False)[0]

    built = {
        "account_health": account_health_dialog.AccountHealthDialog(profile_id=ids[0], db_path=db),
        "add_profile": add_profile_dialog.AddProfileDialog(prof, proj, prox, vault=vault),
        "api_cookie": api_cookie_dialog.ApiCookieDialog(vault=vault),
        "assign_project": assign_project_dialog.AssignProjectDialog(ids, prof, proj),
        "assign_proxy": assign_proxy_dialog.AssignProxyDialog(ids, prof, prox),
        "batch_channel_update": batch_channel_update_dialog.BatchChannelUpdateDialog(
            ids, profile_repo=prof, db_path=db
        ),
        "batch_folder_upload": batch_folder_upload_dialog.BatchFolderUploadDialog(
            profile_repo=prof,
            upload_service=MagicMock(),
            project_id=p1,
            project_name="Kênh Nhật Bản",
            project_repo=proj,
        ),
        "bulk_add_profile": bulk_add_profile_dialog.BulkAddProfileDialog(prof, proj, prox),
        "bulk_edit_profile": bulk_edit_profile_dialog.BulkEditProfileDialog(ids, prof, proj),
        "channel_radar": channel_radar_dialog.ChannelRadarDialog(ids[0], prof, db_path=db),
        "permissions": permissions_dialog.PermissionsDialog(),
        "project_manager": project_dialog.ProjectManagerDialog(proj),
        "proxy_manager": proxy_dialog.ProxyManagerDialog(prox, MagicMock()),
        "schedule_video": schedule_dialog.ScheduleVideoDialog(5),
        "sync_transfer": sync_transfer_dialog.SyncTransferDialog(proj, prof, prox),
        "table_settings": table_settings_dialog.TableSettingsDialog({3}),
        "trash": trash_dialog.TrashDialog(prof),
        "user_guide": user_guide_dialog.UserGuideDialog(),
        "video_metadata": video_metadata_dialog.VideoMetadataDialog(vrow),
    }
    for dlg in built.values():
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)  # real platform, never on screen
        dlg.show()
    for _ in range(5):
        app.processEvents()
    yield built
    for dlg in built.values():
        dlg.close()
        dlg.deleteLater()
    app.processEvents()


def _widgets(dlg: QDialog, cls) -> list:
    return [w for w in dlg.findChildren(cls) if w.isVisibleTo(dlg)]


def _is_ours(w: QWidget) -> bool:
    """Widgets created by our code (not internals of qfluentwidgets composites)."""
    p = w.parent()
    while p is not None:
        if type(p).__module__.startswith("qfluentwidgets"):
            return False
        p = p.parent()
    return True


def _ui_texts(dlg: QDialog) -> list[tuple[str, str]]:
    texts = [("window", dlg.windowTitle())]
    texts += [(type(b).__name__, b.text()) for b in _widgets(dlg, QAbstractButton)]
    texts += [("QGroupBox", g.title()) for g in _widgets(dlg, QGroupBox)]
    for tabs in _widgets(dlg, QTabWidget):
        texts += [("tab", tabs.tabText(i)) for i in range(tabs.count())]
    return [(k, t) for k, t in texts if t]


def test_spin_boxes_show_their_value(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        for spin in _widgets(dlg, QAbstractSpinBox):
            edit = spin.lineEdit()
            if edit.width() < max(20, spin.width() * 0.3):
                bad.append(f"{name}: {type(spin).__name__} text area {edit.width()}px of {spin.width()}px")
    assert not bad, "\n".join(bad)


def test_no_ampersand_is_eaten_as_mnemonic(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        for kind, text in _ui_texts(dlg):
            if kind == "window":
                continue
            if re.search(r"(?<!&)&(?!&)", text):
                bad.append(f"{name}: {kind} {text!r}")
    assert not bad, "single '&' renders as an underlined mnemonic and disappears:\n" + "\n".join(bad)


def test_header_banner_is_not_stretched(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        layout = dlg.layout()
        header = layout.itemAt(0).widget() if layout and layout.count() else None
        if header is None:
            bad.append(f"{name}: no header widget first in layout")
            continue
        if header.height() > header.sizeHint().height() + 6:
            bad.append(f"{name}: header {header.height()}px > hint {header.sizeHint().height()}px")
    assert not bad, "\n".join(bad)


def test_only_fluent_widgets_are_used(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        for w in dlg.findChildren(QWidget):
            if type(w) in RAW_QT and _is_ours(w) and not isinstance(w.parent(), QAbstractSpinBox):
                bad.append(f"{name}: raw {type(w).__name__} {getattr(w, 'text', lambda: '')()!r}")
    assert not bad, "\n".join(bad)


def test_dialogs_follow_the_light_theme(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        img = dlg.grab().toImage()
        total, n = 0.0, 0
        for y in range(0, img.height(), 12):
            for x in range(0, img.width(), 12):
                c = img.pixelColor(x, y)
                total += 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
                n += 1
        if n and total / n < 0.6:
            bad.append(f"{name}: mean luminance {total / n:.2f} (forced dark styling)")
    assert not bad, "\n".join(bad)


def test_no_emoji_in_ui_chrome(dialogs):
    bad = []
    for name, dlg in dialogs.items():
        texts = _ui_texts(dlg)
        texts += [("QLabel", lbl.text()) for lbl in _widgets(dlg, QLabel) if not isinstance(lbl.parent(), QTextBrowser)]
        bad += [f"{name}: {kind} {text!r}" for kind, text in texts if EMOJI.search(text)]
    assert not bad, "use FluentIcon instead of emoji:\n" + "\n".join(bad)


def test_buttons_and_checkboxes_are_not_clipped(dialogs):
    if QGuiApplication.platformName() == "offscreen":
        pytest.skip("offscreen platform has no real font metrics; run on the native platform")
    bad = []
    for name, dlg in dialogs.items():
        for b in _widgets(dlg, QAbstractButton):
            if b.text() and _is_ours(b) and b.width() + 2 < b.sizeHint().width():
                bad.append(f"{name}: {type(b).__name__} {b.text()!r} {b.width()}px < {b.sizeHint().width()}px")
    assert not bad, "\n".join(bad)


def test_shared_dialog_helpers_exist():
    from src.presentation.dialogs import dialog_helpers as h

    assert callable(h.style_group_box) and callable(h.style_tab_widget)
    assert Path("src/presentation/widgets/fluent_compat.py").exists()
