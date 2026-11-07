"""Profile table columns must show real database data (audit 2026-11-07 on the real DB):

- "TS" read a non-existent field and showed "Yes" for every profile, "STT" (25) duplicated column 0, "MP" read a
  non-existent field (always 0). They are replaced by real data: T.Likes (``total_likes``, 44 profiles) and Shadowban.
- ``shadowban_status`` defaults to 'safe' in the schema: only a measured status (traffic source data) is shown.
- the column count ("28 cột MMO") was hard-coded in 6 places; it now follows the header list.
- the "Cấu hình luồng check" value was lost at every restart; "Đồng bộ Profile GoLogin SDK (22+ có sẵn)" showed a
  made-up count (the daemon held 220 profiles).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from src.presentation.widgets.table_helpers import (
    PROFILE_COL_ID,
    get_profile_table_headers,
    migrate_hidden_profile_columns,
)


def test_headers_are_real_unique_and_keep_the_status_column():
    headers = get_profile_table_headers()
    assert len(headers) == 28
    assert len(set(headers)) == len(headers), "duplicate column names"
    assert not {"TS", "MP"} & set(headers)
    assert headers[12] == "Tình trạng"  # StatusBadgeDelegate is bound to column 12
    assert headers[24] == "T.Likes" and headers[25] == "Shadowban" and headers[26] == "VVP"
    assert headers[PROFILE_COL_ID] == "ID" and PROFILE_COL_ID == len(headers) - 1


@pytest.mark.parametrize(
    "saved, version, expected",
    [
        ("3,5,24,26,28", None, {3, 5, 26, 27}),  # old layout: VVP stays 26, ID 28 -> 27, TS/STT/MP dropped
        ("3,25,27", None, {3}),
        ("", None, set()),
        ("3,24,27", "2", {3, 24, 27}),  # already the new layout
        ("x,3", None, {3}),
    ],
)
def test_saved_hidden_columns_are_moved_to_the_new_layout(saved, version, expected):
    assert migrate_hidden_profile_columns(saved, version) == expected


def _row(table, profile):
    table.load_profiles([profile])
    return {i: (table.item(0, i).text() if table.item(0, i) else "") for i in range(table.columnCount())}


def test_new_columns_show_real_values(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    measured = {"id": 78, "name": "swall.pain", "total_likes": 1234567, "shadowban_status": "warning",
                "traffic_source_json": json.dumps({"for_you": 40.0})}
    cells = _row(table, measured)
    assert cells[24] not in ("", "0") and "1" in cells[24]
    assert cells[25] == "Cảnh báo"
    assert cells[PROFILE_COL_ID] == "78"

    unmeasured = {"id": 5, "name": "x", "shadowban_status": "safe"}  # schema default, never measured
    cells = _row(table, unmeasured)
    assert cells[25] == "—"
    assert cells[24] in ("0", "—")


def test_selected_ids_and_double_click_use_the_id_column(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles([{"id": 42, "name": "a"}])
    table.item(0, 0).setData(Qt.ItemDataRole.UserRole, None)  # force the ID-column fallback
    table.selectRow(0)
    assert table.get_selected_profile_ids() == [42]
    hits = []
    table.open_orbita_requested.connect(hits.append)
    table._on_cell_double_clicked(0, 3)
    assert hits == [[42]]


def test_column_count_is_not_hard_coded_in_the_table_dialog_or_menu():
    root = Path(__file__).resolve().parents[2] / "src" / "presentation"
    files = ["dialogs/table_settings_dialog.py", "views/main_window.py", "widgets/profile_table_widget.py"]
    offenders = [
        f for f in files if any(s in (root / f).read_text(encoding="utf-8") for s in ("28 Cột", "28 cột", "22+ có sẵn"))
    ]
    assert offenders == []


def test_table_settings_dialog_title_and_boxes_follow_the_headers(qtbot):
    from src.presentation.dialogs.table_settings_dialog import TableSettingsDialog

    n = len(get_profile_table_headers())
    with patch("src.presentation.dialogs.table_settings_dialog.get_profile_table_headers",
               return_value=[f"C{i}" for i in range(n + 2)]):
        dlg = TableSettingsDialog()
    qtbot.addWidget(dlg)
    assert len(dlg._checkboxes) == n + 2
    assert f"{n + 2} cột" in dlg.windowTitle().lower()


def test_thread_count_survives_a_restart(qapp, tmp_path):
    from src.application.workers.task_worker import drain_ui_tasks
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db = tmp_path / "mw.db"
    run_all_migrations(db)

    def make():
        with patch("src.presentation.views.main_window.MetricsSyncWorker"), \
                patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"), \
                patch("src.presentation.views.main_window.setTheme"):
            win = TikTokManagerMainWindow(db_path=db)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        drain_ui_tasks()
        return win

    win = make()
    with patch("PyQt6.QtWidgets.QInputDialog.getInt", return_value=(4, True)), \
            patch("src.presentation.views.main_window.InfoBar"):
        win._on_configure_concurrency()
    assert win.thread_pool.max_thread_count == 4
    win.close()

    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()  # a new process starts with the default pool
    win2 = make()
    try:
        assert win2.thread_pool.max_thread_count == 4
        labels = [a.text() for a in win2.settings_menu.actions()]
        assert any("(4 luồng)" in t for t in labels)
    finally:
        win2.close()


# --- found by comparing every column of profile 78 with the real database ---------------------------------------


def test_missing_email_is_blank_not_none(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    cells = _row(table, {"id": 1, "name": "a", "email": None, "notes": None})
    assert cells[11] == "" and cells[20] == ""


@pytest.mark.parametrize("strikes, prefix", [(1, "🟡"), (2, "🔴"), (3, "🔴")])
def test_strike_colour_matches_the_account_health_dialog(qtbot, strikes, prefix):
    """1 strike is "Warning" (🟡) in the health dialog; the table showed 🔴."""
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    cells = _row(table, {"id": 1, "name": "a", "strike_count": strikes, "account_standing": "Warning"})
    assert cells[16].startswith(prefix) and f"{strikes}/3" in cells[16]


@pytest.fixture
def sniffer_db(tmp_path):
    from src.infrastructure.database.connection import get_db_connection
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository

    db = tmp_path / "app.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create({"name": "ch"})
    conn = get_db_connection(db)
    for vid, views in (("v1", 100_000), ("v2", 200_000)):  # videos seen in earlier pages / syncs
        conn.execute("INSERT INTO statisticTable (profile_id, id_video, views) VALUES (?, ?, ?)", (pid, vid, views))
    conn.commit()
    conn.close()
    return db, pid


def _total_and_month(db, pid):
    from src.infrastructure.database.connection import get_db_connection

    conn = get_db_connection(db)
    row = conn.execute("SELECT total_views, views_month FROM profiles WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row["total_views"], row["views_month"]


def test_total_views_is_the_sum_of_every_known_video(sniffer_db):
    """Live: T.Views showed 296,097 (the 30-day sum) while the channel's videos total 1.83 M."""
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    db, pid = sniffer_db
    page = {"item_list": [{"item_id": "v3", "play_count": "50000", "create_time": 1700000000}]}
    TikTokNetworkSniffer(db_path=db).process_api_response(
        pid, "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/", page
    )
    assert _total_and_month(db, pid)[0] == 350_000


def test_thirty_day_analytics_do_not_overwrite_total_views(sniffer_db):
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    db, pid = sniffer_db
    sniffer = TikTokNetworkSniffer(db_path=db)
    sniffer.process_api_response(pid, "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/",
                                 {"item_list": [{"item_id": "v3", "play_count": "50000"}]})
    sniffer.process_api_response(
        pid,
        "https://www.tiktok.com/tiktok/v1/analytics/insights/",
        {"analytics_overview_views": {"list": {"value": [{"value": 1000}, {"value": 2000}]}}},
    )
    sniffer.process_api_response(
        pid,
        "https://www.tiktok.com/aweme/v2/data/insight/",
        {"vv_history": [{"value": 4000}, {"value": 5000}]},
    )
    total, month = _total_and_month(db, pid)
    assert total == 350_000
    assert month == 9_000
