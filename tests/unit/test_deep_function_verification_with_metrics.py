"""
Deep granular function-by-function verification with exact verified numerical assertions.
Tests schema, repositories, services, math algorithms, table widgets, dialogs, and MainWindow synchronization.
Strict TDD - Verification Suite.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog
from src.presentation.dialogs.schedule_dialog import (
    generate_staggered_schedule,
    round_to_nearest_5_minutes,
)
from src.presentation.views.main_window import TikTokManagerMainWindow
from src.presentation.widgets.table_helpers import get_video_table_headers
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def metric_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "metric_verification.db"
    run_all_migrations(db_file)
    return db_file


# ---------------------------------------------------------------------------
# 1. ProjectRepository CRUD and Video Folder Persistence Verification
# ---------------------------------------------------------------------------
def test_metric_project_repository_crud_and_video_folder_path(metric_db: Path):
    """Verifies ProjectRepository creates, persists, and updates video_folder with exact data validation."""
    repo = ProjectRepository(metric_db)

    # 1. Create 3 distinct projects (DB migration pre-seeds default project ID 1)
    p1 = repo.create(name="Nhóm Japan", description="Kênh Nhật Bản", video_folder="D:/videos/Japan")
    p2 = repo.create(name="Nhóm Hàn Quốc", description="Kênh Hàn Quốc", video_folder="D:/videos/Korea")
    p3 = repo.create(name="Nhóm US Global", description="Kênh Quốc Tế", video_folder="D:/videos/US")

    assert p1 == 2, f"Expected project ID 2 (after default project 1), got {p1}"
    assert p2 == 3, f"Expected project ID 3, got {p2}"
    assert p3 == 4, f"Expected project ID 4, got {p3}"

    # 2. Verify exact records (1 default + 3 created = 4 total)
    all_projects = repo.list_all()
    assert len(all_projects) == 4, f"Expected 4 projects (1 default + 3 created), got {len(all_projects)}"

    rec1 = repo.get_by_id(p1)
    assert rec1 is not None
    assert rec1["name"] == "Nhóm Japan"
    assert rec1["video_folder"] == "D:/videos/Japan"

    # 3. Update video folder path
    updated = repo.update(p1, video_folder="D:/videos/Japan_Storage_V2")
    assert updated is True

    rec1_updated = repo.get_by_id(p1)
    assert rec1_updated["video_folder"] == "D:/videos/Japan_Storage_V2"


# ---------------------------------------------------------------------------
# 2. VideoRepository Filter Matrix with Project JOIN Metrics
# ---------------------------------------------------------------------------
def test_metric_video_repository_list_available_matrix(metric_db: Path):
    """
    Verifies list_available(project_id) accurately partitions videos by campaign:
    - 4 videos assigned to Japan profiles
    - 3 videos assigned to Korea profiles
    - 2 videos assigned to US profiles
    - 1 unassigned video (available to all)
    Total videos = 10.
    """
    proj_repo = ProjectRepository(metric_db)
    prof_repo = ProfileRepository(metric_db)
    video_repo = VideoRepository(metric_db)

    pj_id = proj_repo.create(name="Market Japan")
    pk_id = proj_repo.create(name="Market Korea")
    pu_id = proj_repo.create(name="Market US")

    # Create 1 profile per project
    prof_jp = prof_repo.create({"uuid": "u-jp", "name": "JP Acc", "project_id": pj_id, "storage_dir": "/jp"})
    prof_kr = prof_repo.create({"uuid": "u-kr", "name": "KR Acc", "project_id": pk_id, "storage_dir": "/kr"})
    prof_us = prof_repo.create({"uuid": "u-us", "name": "US Acc", "project_id": pu_id, "storage_dir": "/us"})

    # 4 Japan videos
    for i in range(1, 5):
        video_repo.register_or_update(
            f"h_jp_{i}", f"C:/jp_{i}.mp4", f"Japan Video {i}", 1000 * i, 10.0, assigned_profile_id=prof_jp
        )

    # 3 Korea videos
    for i in range(1, 4):
        video_repo.register_or_update(
            f"h_kr_{i}", f"C:/kr_{i}.mp4", f"Korea Video {i}", 2000 * i, 15.0, assigned_profile_id=prof_kr
        )

    # 2 US videos
    for i in range(1, 3):
        video_repo.register_or_update(
            f"h_us_{i}", f"C:/us_{i}.mp4", f"US Video {i}", 3000 * i, 20.0, assigned_profile_id=prof_us
        )

    # 1 Unassigned video
    video_repo.register_or_update("h_unassigned", "C:/shared.mp4", "Shared Video", 500, 5.0, assigned_profile_id=None)

    # Assert metric partitioning
    jp_videos = video_repo.list_available(project_id=pj_id)
    assert len(jp_videos) == 5, f"Japan project should have 4 assigned + 1 shared = 5 videos, got {len(jp_videos)}"
    for v in jp_videos:
        if v["assigned_profile_id"] is not None:
            assert v["project_name"] == "Market Japan"
            assert v["assigned_profile_name"] == "JP Acc"

    kr_videos = video_repo.list_available(project_id=pk_id)
    assert len(kr_videos) == 4, f"Korea project should have 3 assigned + 1 shared = 4 videos, got {len(kr_videos)}"
    for v in kr_videos:
        if v["assigned_profile_id"] is not None:
            assert v["project_name"] == "Market Korea"

    us_videos = video_repo.list_available(project_id=pu_id)
    assert len(us_videos) == 3, f"US project should have 2 assigned + 1 shared = 3 videos, got {len(us_videos)}"

    all_videos = video_repo.list_available(project_id=None)
    assert len(all_videos) == 10, f"Total available videos across all projects must be 10, got {len(all_videos)}"


# ---------------------------------------------------------------------------
# 3. Recursive Scanning, Deduplication, and Isolation Directory Filtering
# ---------------------------------------------------------------------------
def test_metric_recursive_scan_and_deduplication_isolation(metric_db: Path, tmp_path: Path):
    """
    Verifies UploadService recursively discovers nested media files across arbitrary subdirectory depths,
    excludes _posted/.posted folders, and filters duplicate file hashes.
    """
    prof_repo = ProfileRepository(metric_db)
    video_repo = VideoRepository(metric_db)
    adapter = MagicMock()
    service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    p_id = prof_repo.create({"uuid": "u-scan", "name": "Scan Profile", "storage_dir": "/sp"})

    root_dir = tmp_path / "Videos_Campaign"
    deep_dir = root_dir / "Sub1" / "Sub2" / "Sub3"
    deep_dir.mkdir(parents=True)

    # 5 Unique valid videos across folder levels
    (root_dir / "clip1.mp4").write_bytes(b"DATA_CLIP_1" + b"\x00" * 1000)
    (root_dir / "Sub1" / "clip2.mov").write_bytes(b"DATA_CLIP_2" + b"\x00" * 1000)
    (root_dir / "Sub1" / "Sub2" / "clip3.mkv").write_bytes(b"DATA_CLIP_3" + b"\x00" * 1000)
    (deep_dir / "clip4.webm").write_bytes(b"DATA_CLIP_4" + b"\x00" * 1000)
    (deep_dir / "clip5.avi").write_bytes(b"DATA_CLIP_5" + b"\x00" * 1000)

    # Non-video file (must be ignored)
    (root_dir / "readme.txt").write_text("not a video")
    (deep_dir / "cover.jpg").write_bytes(b"JPEG_HEADER")

    # Videos inside _posted and .posted folders (must be ignored)
    posted_dir = root_dir / "_posted"
    posted_dir.mkdir()
    (posted_dir / "old_clip.mp4").write_bytes(b"POSTED_VIDEO_1")

    dot_posted_dir = deep_dir / ".posted"
    dot_posted_dir.mkdir()
    (dot_posted_dir / "archived_clip.mov").write_bytes(b"POSTED_VIDEO_2")

    # Duplicate video (exact duplicate content of clip1.mp4 in a separate folder)
    dup_dir = root_dir / "Duplicates"
    dup_dir.mkdir()
    (dup_dir / "clip1_copy.mp4").write_bytes(b"DATA_CLIP_1" + b"\x00" * 1000)

    # Execute batch distribution
    distributed = service.distribute_folder_videos_to_queue(
        folder_path=str(root_dir),
        profile_ids=[p_id],
        deduplicate=True,
    )

    # Exactly 5 unique videos should be indexed
    assert len(distributed) == 5, f"Expected exactly 5 unique videos distributed, got {len(distributed)}"
    names = [Path(d["file_path"]).name for d in distributed]
    # Exactly one copy of the duplicate content is retained, the other deduplicated
    assert any(n in ("clip1.mp4", "clip1_copy.mp4") for n in names)
    assert not (("clip1.mp4" in names) and ("clip1_copy.mp4" in names))
    assert "clip2.mov" in names
    assert "clip3.mkv" in names
    assert "clip4.webm" in names
    assert "clip5.avi" in names
    assert "old_clip.mp4" not in names  # Filtered by _posted exclusion
    assert "archived_clip.mov" not in names  # Filtered by .posted exclusion


# ---------------------------------------------------------------------------
# 4. Fair-Share Round-Robin and Staggered Slot Distribution Metrics
# ---------------------------------------------------------------------------
def test_metric_fair_share_round_robin_and_interval_slots(metric_db: Path, tmp_path: Path):
    """
    Verifies 10 videos distributed across 3 profiles:
    - Profile 1: 4 videos
    - Profile 2: 3 videos
    - Profile 3: 3 videos
    - Offset formula: slot_offset_min = 5 + idx * (min_interval_hours * 60)
    """
    prof_repo = ProfileRepository(metric_db)
    video_repo = VideoRepository(metric_db)
    adapter = MagicMock()
    service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    prof1 = prof_repo.create({"uuid": "u-rr-1", "name": "Channel Alpha", "storage_dir": "/a"})
    prof2 = prof_repo.create({"uuid": "u-rr-2", "name": "Channel Beta", "storage_dir": "/b"})
    prof3 = prof_repo.create({"uuid": "u-rr-3", "name": "Channel Gamma", "storage_dir": "/c"})

    video_folder = tmp_path / "10_videos"
    video_folder.mkdir()
    for i in range(1, 11):
        (video_folder / f"video_{i:02d}.mp4").write_bytes(f"DATA_{i}".encode() + b"\x00" * 1000)

    # 1.5 hours interval (90 minutes)
    items = service.distribute_folder_videos_to_queue(
        folder_path=str(video_folder),
        profile_ids=[prof1, prof2, prof3],
        min_interval_hours=1.5,
        random_order=False,  # deterministic order
    )

    assert len(items) == 10

    # Count distribution per profile
    p1_items = [item for item in items if item["assigned_profile_id"] == prof1]
    p2_items = [item for item in items if item["assigned_profile_id"] == prof2]
    p3_items = [item for item in items if item["assigned_profile_id"] == prof3]

    assert len(p1_items) == 4, f"Profile 1 must receive 4 videos, got {len(p1_items)}"
    assert len(p2_items) == 3, f"Profile 2 must receive 3 videos, got {len(p2_items)}"
    assert len(p3_items) == 3, f"Profile 3 must receive 3 videos, got {len(p3_items)}"

    # Check timing progression: Each video must be spaced by ~90 minutes
    times = [datetime.strptime(item["schedule_time"], "%Y-%m-%d %H:%M:%S") for item in items]
    for idx in range(1, len(times)):
        delta_minutes = (times[idx] - times[idx - 1]).total_seconds() / 60
        assert round(delta_minutes) == 90, (
            f"Expected 90m interval between video {idx - 1} and {idx}, got {delta_minutes}"
        )


# ---------------------------------------------------------------------------
# 5. TikTok Studio Native Cloud Schedule Math & Bounds Verification
# ---------------------------------------------------------------------------
def test_metric_tiktok_studio_schedule_rounding_and_window_bounds():
    """
    Verifies:
    1. round_to_nearest_5_minutes accurately snaps to 0, 5, 10, ..., 55.
    2. generate_staggered_schedule enforces 15m min delay, 10-day max delay, 5-minute multiples.
    """
    test_cases = [
        (0, 0),
        (1, 0),
        (2, 0),
        (3, 5),
        (4, 5),
        (5, 5),
        (6, 5),
        (7, 5),
        (8, 10),
        (12, 10),
        (13, 15),
        (28, 30),
        (32, 30),
        (52, 50),
        (53, 55),
        (57, 55),
        (59, 55),
    ]
    for minute_in, expected_rounded in test_cases:
        actual = round_to_nearest_5_minutes(minute_in)
        assert actual == expected_rounded, f"Input {minute_in} expected {expected_rounded}, got {actual}"

    # Verify studio schedule bounds
    now = datetime.now()
    start = now + timedelta(minutes=5)  # Less than 15 min ahead

    schedules = generate_staggered_schedule(
        start_time=start,
        count=15,
        interval_minutes=30,
        random_jitter_minutes=5,
        is_studio_schedule=True,
    )

    assert len(schedules) == 15
    for s_str in schedules:
        dt = datetime.strptime(s_str, "%Y-%m-%d %H:%M:%S")
        # Seconds must be zero
        assert dt.second == 0, f"Studio schedule seconds must be 0, got {dt.second}"
        # Minutes must be multiple of 5
        assert dt.minute % 5 == 0, f"Studio schedule minute must be multiple of 5, got {dt.minute}"
        # At least 14 minutes ahead (allowing minor test execution lag)
        assert dt >= now + timedelta(minutes=14), f"Schedule {dt} is sooner than 15m ahead"
        # At most 10 days ahead
        assert dt <= now + timedelta(days=10, hours=1), f"Schedule {dt} exceeds 10 days"


# ---------------------------------------------------------------------------
# 6. VideoQueueTableWidget 15 Columns & Numerical Sorting Metrics
# ---------------------------------------------------------------------------
def test_metric_video_queue_table_widget_15_columns_and_sorting(qapp):
    """Verifies VideoQueueTableWidget exact 15-column schema and numeric sort stability."""
    table = VideoQueueTableWidget()
    headers = get_video_table_headers()
    assert len(headers) == 15
    assert table.columnCount() == 15

    expected_headers = [
        "STT",
        "Tiêu đề",
        "Dự Án",
        "Lượt view",
        "Lượt like",
        "Duration",
        "Hiển thị",
        "Lên lịch",
        "Upload To",
        "Tình trạng",
        "Source",
        "Link gốc",
        "ID Video",
        "PVF URL",
        "PAF URL",
    ]
    for idx, expected in enumerate(expected_headers):
        assert table.horizontalHeaderItem(idx).text() == expected, (
            f"Col {idx} expected {expected}, got {table.horizontalHeaderItem(idx).text()}"
        )

    # Load records with diverse numeric metrics
    records = [
        {"id": 1, "file_name": "Vid A", "views": 1000, "duration": 60.0, "project_name": "Japan"},
        {"id": 2, "file_name": "Vid B", "views": 25, "duration": 15.0, "project_name": "Korea"},
        {"id": 3, "file_name": "Vid C", "views": 500000, "duration": 120.0, "file_path": "D:/vids/US/clip.mp4"},
        {"id": 4, "file_name": "Vid D", "views": 5, "duration": 7.0, "project_name": None, "file_path": None},
    ]
    table.load_videos(records)
    assert table.rowCount() == 4

    # Verify Project column rendering
    assert table.item(0, 2).text() == "Japan"
    assert table.item(1, 2).text() == "Korea"
    assert table.item(2, 2).text() == "US"  # Fallback to parent folder
    assert table.item(3, 2).text() == "Chung"  # Fallback to Chung

    # Sort numerically by Views (Col 3)
    table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
    sorted_views = [
        table.item(r, 3).raw_value for r in range(table.rowCount()) if hasattr(table.item(r, 3), "raw_value")
    ]
    assert sorted_views == [5, 25, 1000, 500000], f"Expected numeric sort [5, 25, 1000, 500000], got {sorted_views}"
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 7. BatchFolderUploadDialog Live Counter & Banner Metrics
# ---------------------------------------------------------------------------
def test_metric_batch_folder_upload_dialog_live_counter_and_banner(qapp, metric_db: Path, tmp_path: Path):
    """Verifies BatchFolderUploadDialog updates file count and displays project badge."""
    prof_repo = ProfileRepository(metric_db)
    proj_repo = ProjectRepository(metric_db)
    video_repo = VideoRepository(metric_db)
    adapter = MagicMock()
    service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    p_id = proj_repo.create(name="Dự Án Nhật Bản (Tokyo 2026)")
    prof_repo.create({"uuid": "u-tokyo", "name": "Tokyo Channel", "project_id": p_id, "storage_dir": "/t"})

    folder = tmp_path / "Tokyo_Files"
    folder.mkdir()
    (folder / "tokyo_01.mp4").write_bytes(b"DATA" + b"\x00" * 1000)
    (folder / "tokyo_02.mov").write_bytes(b"DATA" + b"\x00" * 1000)
    (folder / "tokyo_03.mkv").write_bytes(b"DATA" + b"\x00" * 1000)

    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=service,
        initial_folder=str(folder),
        project_id=p_id,
        project_name="Dự Án Nhật Bản (Tokyo 2026)",
    )

    # Banner verification
    assert "Dự Án Nhật Bản (Tokyo 2026)" in dlg.lbl_project_badge.text()

    # Counter verification
    assert "3 video" in dlg.lbl_scan_info.text()
    assert dlg.profile_table.rowCount() == 1  # Only Tokyo Channel loaded

    # Update folder dynamically
    empty_folder = tmp_path / "Empty_Folder"
    empty_folder.mkdir()
    dlg.txt_folder.setText(str(empty_folder))
    assert "chưa có file video" in dlg.lbl_scan_info.text().lower()


# ---------------------------------------------------------------------------
# 8. MainWindow End-to-End Synchronization Pipeline Verification
# ---------------------------------------------------------------------------
def test_metric_main_window_full_synchronization_pipeline(qapp, metric_db: Path, monkeypatch, tmp_path: Path):
    """
    Verifies MainWindow dual-table synchronization when switching projects:
    - 2 Projects (Japan, Korea)
    - Switching projects dynamically updates both ProfileTable and VideoTable row counts
    - Toolbar Studio schedule checkbox exists and connects to ScheduleVideoDialog
    """
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    proj_repo = ProjectRepository(metric_db)
    prof_repo = ProfileRepository(metric_db)
    video_repo = VideoRepository(metric_db)

    # Setup Japan (Project 1)
    folder_jp = tmp_path / "Videos_JP"
    folder_jp.mkdir()
    p1 = proj_repo.create(name="Nhóm Japan", video_folder=str(folder_jp))
    p1_prof1 = prof_repo.create({"uuid": "u-jp-1", "name": "JP Acc 1", "project_id": p1, "storage_dir": "/jp1"})
    p1_prof2 = prof_repo.create({"uuid": "u-jp-2", "name": "JP Acc 2", "project_id": p1, "storage_dir": "/jp2"})
    video_repo.register_or_update("h_jp_v1", "C:/v_jp1.mp4", "Video JP 1", 100, 1.0, assigned_profile_id=p1_prof1)
    video_repo.register_or_update("h_jp_v2", "C:/v_jp2.mp4", "Video JP 2", 100, 1.0, assigned_profile_id=p1_prof2)
    video_repo.register_or_update("h_jp_v3", "C:/v_jp3.mp4", "Video JP 3", 100, 1.0, assigned_profile_id=p1_prof1)

    # Setup Korea (Project 2)
    folder_kr = tmp_path / "Videos_KR"
    folder_kr.mkdir()
    p2 = proj_repo.create(name="Nhóm Korea", video_folder=str(folder_kr))
    p2_prof1 = prof_repo.create({"uuid": "u-kr-1", "name": "KR Acc 1", "project_id": p2, "storage_dir": "/kr1"})
    video_repo.register_or_update("h_kr_v1", "C:/v_kr1.mp4", "Video KR 1", 100, 1.0, assigned_profile_id=p2_prof1)

    # Launch MainWindow
    window = TikTokManagerMainWindow(db_path=metric_db)
    try:
        # Check toolbar streamlined button labels
        assert window.btn_batch_upload.text() == "Nạp Thư Mục Phân Bổ"
        assert window.btn_pick_pc.text() == "Thêm Video"
        assert window.btn_schedule.text() == "Lên lịch"
        assert window.btn_start_upload.text() == "Bắt đầu Upload"
        assert window.search_video.placeholderText() == "Tìm kiếm video trong bảng..."

        # Initially "Tất cả dự án": 3 profiles (2 JP + 1 KR), 4 videos (3 JP + 1 KR)
        assert window.profile_table.rowCount() == 3
        assert window.video_table.rowCount() == 4

        # Switch to "Nhóm Japan"
        jp_idx = -1
        for i in range(window.project_combo.count()):
            if window.project_combo.itemData(i) == p1:
                jp_idx = i
                break
        assert jp_idx > 0
        window.project_combo.setCurrentIndex(jp_idx)

        # Verified Metrics for Japan
        assert window.profile_table.rowCount() == 2, (
            f"Japan should show 2 profiles, got {window.profile_table.rowCount()}"
        )
        assert window.video_table.rowCount() == 3, f"Japan should show 3 videos, got {window.video_table.rowCount()}"

        # Switch to "Nhóm Korea"
        kr_idx = -1
        for i in range(window.project_combo.count()):
            if window.project_combo.itemData(i) == p2:
                kr_idx = i
                break
        assert kr_idx > 0
        window.project_combo.setCurrentIndex(kr_idx)

        # Verified Metrics for Korea
        assert window.profile_table.rowCount() == 1, (
            f"Korea should show 1 profile, got {window.profile_table.rowCount()}"
        )
        assert window.video_table.rowCount() == 1, f"Korea should show 1 video, got {window.video_table.rowCount()}"

        # Switch back to "Tất cả dự án"
        window.project_combo.setCurrentIndex(0)
        assert window.profile_table.rowCount() == 3
        assert window.video_table.rowCount() == 4

        # Verify scheduling modal dialog triggers cleanly
        window._on_schedule_videos()

    finally:
        window.scheduler_timer.stop()
        window.close()
        window.deleteLater()
        qapp.processEvents()
