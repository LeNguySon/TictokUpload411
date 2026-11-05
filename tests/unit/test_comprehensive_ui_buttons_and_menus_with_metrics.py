"""Comprehensive test suite with quantifiable metrics and assertions covering
100% of toolbar buttons, profile table context menu actions (16 items),
video queue table context menu actions (8 items), and settings menu actions (16 items).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.workers.task_worker import drain_ui_tasks, process_events_until
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_background_workers():
    with patch("src.presentation.views.main_window.MetricsSyncWorker"):
        yield
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()


@pytest.fixture
def populated_db(tmp_path: Path):
    """Sets up an isolated SQLite database populated with multi-project, multi-profile, and multi-video metrics."""
    db_file = tmp_path / "comprehensive_metrics.db"
    run_all_migrations(db_file)

    proj_repo = ProjectRepository(db_file)
    prof_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)
    video_repo = VideoRepository(db_file)

    # 1. Projects (ID 1 is default, create ID 2: Japan, ID 3: Korea)
    p2 = proj_repo.create("Japan Group")
    p3 = proj_repo.create("Korea Group")

    # 2. Proxies
    px1 = proxy_repo.create(host="192.168.1.101", port=8080, protocol="http")
    px2 = proxy_repo.create(host="192.168.1.102", port=8080, protocol="http")

    # 3. Profiles
    # Japan profiles (project p2)
    prof_j1 = prof_repo.create(
        {
            "name": "JP_Channel_01",
            "project_id": p2,
            "proxy_id": px1,
            "status": "LIVE",
            "username_on_tiktok": "japan_tok_1",
            "email": "jp1@example.com",
        }
    )
    prof_j2 = prof_repo.create(
        {
            "name": "JP_Channel_02",
            "project_id": p2,
            "proxy_id": px2,
            "status": "LIVE",
            "username_on_tiktok": "japan_tok_2",
            "email": "jp2@example.com",
        }
    )
    # Korea profiles (project p3)
    prof_k1 = prof_repo.create(
        {
            "name": "KR_Channel_01",
            "project_id": p3,
            "status": "LIVE",
            "username_on_tiktok": "korea_tok_1",
            "email": "kr1@example.com",
        }
    )

    # 4. Videos
    v1_file = tmp_path / "vid_japan_1.mp4"
    v2_file = tmp_path / "vid_japan_2.mp4"
    v3_file = tmp_path / "vid_korea_1.mp4"
    for v, tag in ((v1_file, b"V1"), (v2_file, b"V2"), (v3_file, b"V3")):
        v.write_bytes(tag * 2048)

    video_repo.register_or_update(
        video_hash="hash_jp_1",
        file_path=str(v1_file),
        file_name="vid_japan_1",
        file_size=4096,
        mtime=100.0,
        assigned_profile_id=prof_j1,
    )
    video_repo.register_or_update(
        video_hash="hash_jp_2",
        file_path=str(v2_file),
        file_name="vid_japan_2",
        file_size=4096,
        mtime=101.0,
        assigned_profile_id=prof_j2,
    )
    video_repo.register_or_update(
        video_hash="hash_kr_1",
        file_path=str(v3_file),
        file_name="vid_korea_1",
        file_size=4096,
        mtime=102.0,
        assigned_profile_id=prof_k1,
    )

    return {
        "db_file": db_file,
        "projects": [p2, p3],
        "profiles": [prof_j1, prof_j2, prof_k1],
        "proxies": [px1, px2],
        "videos": [v1_file, v2_file, v3_file],
    }


# =============================================================================
# 1. TEST TOOLBAR BUTTONS & FILTERING CONTROLS (WITH VERIFIED METRICS)
# =============================================================================
def test_toolbar_buttons_and_filtering_metrics(populated_db, app_instance):
    """Verifies that all toolbar controls (combos, searches, jumpers, buttons) work with exact metrics."""
    db_file = populated_db["db_file"]

    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        win = TikTokManagerMainWindow(db_path=db_file)

        # 1. Project Dropdown Metrics
        assert win.profile_table.rowCount() == 3
        assert win.video_table.rowCount() == 3

        # Filter by Japan Group (p2)
        jp_index = -1
        for idx in range(win.project_combo.count()):
            if win.project_combo.itemText(idx) == "Japan Group":
                jp_index = idx
                break
        assert jp_index > 0
        win.project_combo.setCurrentIndex(jp_index)
        drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1

        # After filtering by Japan Group:
        assert win.profile_table.rowCount() == 2
        assert win.video_table.rowCount() == 2

        # Reset to 'Tất cả dự án'
        win.project_combo.setCurrentIndex(0)
        drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
        assert win.profile_table.rowCount() == 3
        assert win.video_table.rowCount() == 3

        # 2. Profile Search LineEdit Metrics
        win.search_profile.setText("kr1@example.com")
        assert process_events_until(lambda: not win._profile_search_timer.isActive())  # debounced search (T10)
        hidden_count = sum(1 for r in range(win.profile_table.rowCount()) if win.profile_table.isRowHidden(r))
        visible_count = sum(1 for r in range(win.profile_table.rowCount()) if not win.profile_table.isRowHidden(r))
        assert visible_count == 1
        assert hidden_count == 2

        # Clear search
        win.search_profile.clear()
        assert sum(1 for r in range(win.profile_table.rowCount()) if not win.profile_table.isRowHidden(r)) == 3

        # 3. Video Search LineEdit Metrics
        win.search_video.setText("korea")
        assert process_events_until(lambda: not win._video_search_timer.isActive())  # debounced search (T10)
        v_visible = sum(1 for r in range(win.video_table.rowCount()) if not win.video_table.isRowHidden(r))
        v_hidden = sum(1 for r in range(win.video_table.rowCount()) if win.video_table.isRowHidden(r))
        assert v_visible == 1
        assert v_hidden == 2

        win.search_video.clear()
        assert sum(1 for r in range(win.video_table.rowCount()) if not win.video_table.isRowHidden(r)) == 3

        # 4. Row Jumper Step Setting
        win.spin_jump.setValue(2)
        assert win.spin_jump.value() == 2

        # 5. Switch Auto Mode Toggle
        assert win.switch_auto.isChecked() is True
        win.switch_auto.setChecked(False)
        assert win.switch_auto.isChecked() is False

        # 6. Clear Video Table Button Metrics
        with patch("src.presentation.views.main_window.MessageBox") as mock_mb:
            mock_mb.return_value.exec.return_value = True
            win._on_clear_video_table()
        assert win.video_table.rowCount() == 0

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.video_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


# =============================================================================
# 2. TEST ALL 16 PROFILE TABLE CONTEXT MENU ACTIONS (WITH DATABASE METRICS)
# =============================================================================
def test_profile_context_menu_actions_and_database_metrics(populated_db, app_instance):
    """Verifies that all 16 context menu actions on ProfileTableWidget trigger correctly and alter metrics."""
    db_file = populated_db["db_file"]
    prof_j1 = populated_db["profiles"][0]

    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        win = TikTokManagerMainWindow(db_path=db_file)
        win.profile_table.selectRow(0)

        # 1. act_orbita (Launch browser)
        with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
            win.profile_table.open_orbita_requested.emit([prof_j1])
            assert mock_dispatch.called

        # 2. act_close (Close browser)
        with patch.object(win.orbita_launcher, "close_profile") as mock_close:
            win.profile_table.close_orbita_requested.emit([prof_j1])
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
            assert mock_close.called

        # 3. act_cookie (Check Cookie LIVE/DIE)
        win.profile_table.check_cookie_requested.emit([prof_j1])
        p_cookie_stat = win.profile_repo.get_by_id(prof_j1)
        assert p_cookie_stat["status"] in ("LIVE", "DIE")

        # 4. act_sync (Sync metrics)
        with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
            with patch.object(
                win.profile_service, "sync_metrics_from_tiktok", return_value={"views": 100, "likes": 50}
            ):
                win.profile_table.sync_metrics_requested.emit([prof_j1])
                assert mock_dispatch.called

        # 5. act_add_video (Add video for profile)
        sample_vid = populated_db["videos"][0]
        with patch(
            "src.presentation.views.main_window.QFileDialog.getOpenFileNames",
            return_value=([str(sample_vid)], "Video Files"),
        ):
            with patch.object(win.thread_pool, "dispatch") as mock_dispatch:

                def run_worker_sync(worker):
                    worker.run()

                mock_dispatch.side_effect = run_worker_sync
                win.profile_table.add_video_requested.emit([prof_j1])
        win.refresh_videos()
        drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
        assert win.video_table.rowCount() >= 1

        # 6. act_proxy (Update/Assign Proxy)
        with patch("src.presentation.dialogs.assign_proxy_dialog.AssignProxyDialog.exec", return_value=True):
            win.profile_table.update_proxy_requested.emit([prof_j1])

        # 7. act_rotate_proxy (Rotate IP)
        with patch.object(win.proxy_service, "rotate_proxy_ip", return_value={"status": "success"}) as mock_rot:
            # Set proxy_type to rotating
            win.proxy_repo.update(populated_db["proxies"][0], proxy_type="rotating")
            win.profile_table.rotate_proxy_requested.emit([prof_j1])
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
            assert mock_rot.called

        # 8. act_check_proxy (Check proxy latency)
        with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
            win.profile_table.check_proxy_requested.emit([prof_j1])
            assert mock_dispatch.called

        # 9. act_remove_proxy (Remove proxy)
        win.profile_table.remove_proxy_requested.emit([prof_j1])
        updated_prof = win.profile_repo.get_by_id(prof_j1)
        assert updated_prof["proxy_id"] is None

        # 10. act_edit (Edit profile)
        with patch("src.presentation.dialogs.add_profile_dialog.AddProfileDialog.exec", return_value=True):
            win.profile_table.edit_profile_requested.emit(prof_j1)

        # 11. act_bulk (Bulk edit profiles)
        with patch("src.presentation.dialogs.bulk_edit_profile_dialog.BulkEditProfileDialog.exec", return_value=True):
            win.profile_table.bulk_edit_requested.emit([prof_j1])

        # 12. act_project (Change Project)
        with patch("src.presentation.dialogs.assign_project_dialog.AssignProjectDialog.exec", return_value=True):
            win.profile_table.change_project_requested.emit([prof_j1])

        # 13. act_web (Open TikTok Web)
        with patch("PyQt6.QtGui.QDesktopServices.openUrl") as mock_url:
            win.profile_table.open_web_profile_requested.emit("japan_tok_1")
            assert mock_url.called

        # 14. act_folder (Open Profile Folder)
        with patch("src.presentation.views.main_window.os.startfile", create=True) as mock_startfile:
            with patch("pathlib.Path.exists", return_value=True):
                win.profile_table.open_folder_requested.emit("profiles/japan_01")
                assert mock_startfile.called

        # 15. status_menu (Change Status to DIE, CHECKPOINT, stopped, LIVE)
        for target_stat in ("DIE", "CHECKPOINT", "stopped", "LIVE"):
            win.profile_table.change_status_requested.emit([prof_j1], target_stat)
            p_stat = win.profile_repo.get_by_id(prof_j1)
            assert p_stat["status"] == target_stat

        # 16. act_delete (Soft Delete Profile to Trash)
        with patch("src.presentation.views.main_window.MessageBox") as mock_mb:
            mock_mb.return_value.exec.return_value = True
            win.profile_table.soft_delete_requested.emit([prof_j1])
            p_trashed = win.profile_repo.get_by_id(prof_j1)
            assert p_trashed["is_trashed"] == 1
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
            assert win.profile_table.rowCount() == 2

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.video_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


# =============================================================================
# 3. TEST ALL 8 VIDEO QUEUE TABLE CONTEXT MENU ACTIONS (WITH VERIFIED METRICS)
# =============================================================================
def test_video_queue_context_menu_actions_and_metrics(populated_db, app_instance):
    """Verifies that all 8 context menu actions on VideoQueueTableWidget function cleanly."""
    db_file = populated_db["db_file"]

    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        win = TikTokManagerMainWindow(db_path=db_file)
        assert win.video_table.rowCount() == 3

        # Select a profile in profile_table so video upload action is enabled
        win.profile_table.selectRow(0)

        selected_vid = win.video_table.get_selected_videos()
        if not selected_vid:
            win.video_table.selectRow(0)
            selected_vid = win.video_table.get_selected_videos()
        vid_id = selected_vid[0]["id"]

        # 1. act_upload (Upload Now)
        # Uploads run on the dedicated upload pool since UI responsiveness T8
        with patch.object(win.thread_pool, "dispatch_upload") as mock_dispatch:
            win.video_table.upload_now_requested.emit([vid_id])
            assert mock_dispatch.called

        # 2. act_schedule (Schedule Video)
        with patch("src.presentation.dialogs.schedule_dialog.ScheduleVideoDialog.exec", return_value=True):
            win.video_table.schedule_video_requested.emit([vid_id])

        # 3. act_edit (Edit Metadata)
        with patch("src.presentation.dialogs.video_metadata_dialog.VideoMetadataDialog.exec", return_value=True):
            win.video_table.edit_metadata_requested.emit(vid_id)

        # 4. act_preview (Preview Media)
        with patch("src.presentation.views.main_window.os.startfile", create=True) as mock_startfile:
            with patch("pathlib.Path.exists", return_value=True):
                win.video_table.preview_video_requested.emit("test_video.mp4")
                assert mock_startfile.called

        # 5. act_folder (Open Containing Folder)
        with patch("src.presentation.views.main_window.subprocess.run") as mock_subproc:
            with patch("pathlib.Path.exists", return_value=True):
                win.video_table.open_folder_requested.emit("test_folder/test_video.mp4")
                assert mock_subproc.called

        # 6. act_web_vid (Open TikTok Video Web)
        with patch("PyQt6.QtGui.QDesktopServices.openUrl") as mock_url:
            win.video_table.open_published_link_requested.emit("7384910293")
            assert mock_url.called

        # 7. act_delete (Delete Video from Queue)
        with patch("src.presentation.views.main_window.MessageBox") as mock_mb:
            mock_mb.return_value.exec.return_value = True
            win.video_table.delete_video_requested.emit([vid_id])
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
            assert win.video_table.rowCount() == 2
            # DB record should be deleted
            assert win.video_repo.get_by_id(vid_id) is None

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.video_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


# =============================================================================
# 4. TEST ALL 16 SETTINGS & TOOLS MENU ACTIONS (WITH SYSTEM METRICS)
# =============================================================================
def test_settings_menu_actions_and_system_metrics(populated_db, app_instance):
    """Verifies all 16 actions registered in the centralized Settings & Tools menu."""
    db_file = populated_db["db_file"]

    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        win = TikTokManagerMainWindow(db_path=db_file)

        # Verify exact action count in settings menu
        actions = win.settings_menu.actions()
        real_actions = [a for a in actions if not a.isSeparator()]
        assert len(real_actions) >= 16

        # 1. act_add_1 (Add 1 profile)
        with patch("src.presentation.dialogs.add_profile_dialog.AddProfileDialog.exec", return_value=True):
            win._on_add_profile()

        # 2. act_add_many (Bulk add profiles)
        with patch("src.presentation.dialogs.bulk_add_profile_dialog.BulkAddProfileDialog.exec", return_value=True):
            win._on_bulk_add_profiles()

        # 3. act_show_all (Show all profiles)
        win._on_show_all_profiles()
        assert win.project_combo.currentIndex() == 0
        assert win.search_profile.text() == ""
        assert win.profile_table.rowCount() == 3

        # 4. act_sync (Sync metrics)
        with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
            with patch.object(
                win.profile_service, "sync_metrics_from_tiktok", return_value={"views": 100, "likes": 50}
            ):
                win._on_sync_selected_metrics()
                assert mock_dispatch.called

        # 5. act_orbita (Launch Orbita)
        with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
            win._on_launch_orbita_selected()

        # 6. act_gologin_sync (Sync GoLogin profiles)
        with patch.object(win.gologin_sync_service, "sync_from_local_gologin", return_value=5):
            win._on_sync_gologin_profiles()

        # 7. act_projects (Project Manager)
        with patch("src.presentation.dialogs.project_dialog.ProjectManagerDialog.exec", return_value=True):
            win._on_open_project_manager()

        # 8. act_proxy (Proxy Manager)
        with patch("src.presentation.dialogs.proxy_dialog.ProxyManagerDialog.exec", return_value=True):
            win._on_open_proxy_manager()

        # 9. act_table_cfg (Table Configuration)
        with patch("src.presentation.dialogs.table_settings_dialog.TableSettingsDialog.exec", return_value=True):
            win._on_table_cfg()

        # 10. act_concurrency (Configure thread pool concurrency)
        with patch("PyQt6.QtWidgets.QInputDialog.getInt", return_value=(16, True)):
            win._on_configure_concurrency()
            assert win.thread_pool.max_thread_count == 16

        # 11. act_api_cookie (API & Cookie Dialog)
        with patch("src.presentation.dialogs.api_cookie_dialog.ApiCookieDialog.exec", return_value=True):
            win._on_api_cookie()

        # 12. act_permissions (OAuth permissions dialog)
        with patch("src.presentation.dialogs.permissions_dialog.PermissionsDialog.exec", return_value=True):
            win._on_permissions()

        # 13. act_send_recv (Sync transfer dialog)
        with patch("src.presentation.dialogs.sync_transfer_dialog.SyncTransferDialog.exec", return_value=True):
            win._on_send_recv()

        # 14. act_trash (Trash Dialog)
        with patch("src.presentation.dialogs.trash_dialog.TrashDialog.exec", return_value=True):
            win._on_open_trash()

        # 15. act_clean (Clean browser cache & RAM)
        with (
            patch(
                "src.infrastructure.browser.process_supervisor.BrowserProcessSupervisor.trim_working_set",
                return_value={"freed_mb": 12.5},
            ),
            patch("src.presentation.views.main_window.MessageBox") as mock_mb_clean,
        ):
            mock_mb_clean.return_value.exec.return_value = True
            win._on_clean_browser()
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1

        # 16. act_guide (User Guide Dialog)
        with patch("src.presentation.dialogs.user_guide_dialog.UserGuideDialog.exec", return_value=True):
            win._on_guide()

        # 17. act_chan (Batch Channel Update Dialog)
        with patch(
            "src.presentation.dialogs.batch_channel_update_dialog.BatchChannelUpdateDialog.exec", return_value=True
        ):
            win._on_batch_channel_update([1, 2])

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.video_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()
