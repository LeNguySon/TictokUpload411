"""
TDD Unit Tests for Automatic Video Physical Isolation (_posted/).
Verifies:
1. move_video_to_posted_folder physical file move & directory creation.
2. Collision resolution (incrementing suffixes _1, _2...).
3. Idempotent behaviour when file is already in _posted.
4. Error handling for missing files.
5. VideoRepository update_metadata supporting file_path & file_name.
6. UploadService.isolate_video_file end-to-end integration with SQLite.
7. VideoQueueTableWidget folder scan ignores _posted and .posted subdirectories.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QMimeData, QUrl
from src.application.services.upload_service import UploadService
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.media.video_isolation import move_video_to_posted_folder
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_isolation.db"
    run_all_migrations(db_file)
    return db_file


def test_move_video_to_posted_folder_basic(tmp_path: Path) -> None:
    video_dir = tmp_path / "my_videos"
    video_dir.mkdir(parents=True)
    video_file = video_dir / "funny_cats.mp4"
    video_file.write_text("dummy video content", encoding="utf-8")

    dest_path = move_video_to_posted_folder(video_file)

    assert dest_path.is_file()
    assert dest_path.name == "funny_cats.mp4"
    assert dest_path.parent.name == "_posted"
    assert dest_path.parent == video_dir / "_posted"
    assert not video_file.exists(), "Original file must be moved, not copied"
    assert dest_path.read_text(encoding="utf-8") == "dummy video content"


def test_move_video_collision_resolution(tmp_path: Path) -> None:
    video_dir = tmp_path / "my_videos"
    posted_dir = video_dir / "_posted"
    posted_dir.mkdir(parents=True)

    # Pre-create conflicting files in _posted
    (posted_dir / "highlight.mp4").write_text("existing clip 0", encoding="utf-8")
    (posted_dir / "highlight_1.mp4").write_text("existing clip 1", encoding="utf-8")

    # New file to move
    src_file = video_dir / "highlight.mp4"
    src_file.write_text("new clip to isolate", encoding="utf-8")

    dest_path = move_video_to_posted_folder(src_file)

    assert dest_path.name == "highlight_2.mp4"
    assert dest_path.is_file()
    assert dest_path.read_text(encoding="utf-8") == "new clip to isolate"
    # Ensure previous files remained intact
    assert (posted_dir / "highlight.mp4").read_text(encoding="utf-8") == "existing clip 0"
    assert (posted_dir / "highlight_1.mp4").read_text(encoding="utf-8") == "existing clip 1"


def test_move_video_idempotent(tmp_path: Path) -> None:
    posted_dir = tmp_path / "clips" / "_posted"
    posted_dir.mkdir(parents=True)
    already_posted = posted_dir / "done.mp4"
    already_posted.write_text("already isolated", encoding="utf-8")

    # Calling move on a file already inside _posted should return the file untouched
    dest_path = move_video_to_posted_folder(already_posted)
    assert dest_path == already_posted
    assert dest_path.exists()


def test_move_video_file_not_found(tmp_path: Path) -> None:
    non_existent = tmp_path / "ghost.mp4"
    with pytest.raises(FileNotFoundError, match="Source video file does not exist"):
        move_video_to_posted_folder(non_existent)


def test_video_repository_update_metadata_path_and_name(temp_db: Path) -> None:
    repo = VideoRepository(temp_db)
    video_id = repo.register_or_update(
        video_hash="hash123",
        file_path="D:/raw/video1.mp4",
        file_name="video1.mp4",
        file_size=1024,
        mtime=100.0,
    )

    # Update both file_name and file_path
    success = repo.update_metadata(video_id, file_name="video1_new.mp4", file_path="D:/raw/_posted/video1_new.mp4")
    assert success is True

    record = repo.get_by_id(video_id)
    assert record is not None
    assert record["file_name"] == "video1_new.mp4"
    assert record["file_path"] == "D:/raw/_posted/video1_new.mp4"


def test_upload_service_isolate_video_file(temp_db: Path, tmp_path: Path) -> None:
    profile_repo = ProfileRepository(temp_db)
    video_repo = VideoRepository(temp_db)
    mock_adapter = MagicMock()

    upload_service = UploadService(
        profile_repo=profile_repo,
        video_repo=video_repo,
        tiktok_adapter=mock_adapter,
    )

    # Create dummy video file on disk
    src_folder = tmp_path / "content"
    src_folder.mkdir()
    video_path = src_folder / "tiktok_dance.mp4"
    video_path.write_text("dance video bytes", encoding="utf-8")

    video_id = video_repo.register_or_update(
        video_hash="hash_dance",
        file_path=str(video_path),
        file_name="tiktok_dance.mp4",
        file_size=video_path.stat().st_size,
        mtime=video_path.stat().st_mtime,
    )

    # Perform isolation
    new_path = upload_service.isolate_video_file(video_id)
    assert new_path is not None
    assert new_path.is_file()
    assert new_path.parent.name == "_posted"
    assert not video_path.exists()

    # Verify SQLite record updated
    record = video_repo.get_by_id(video_id)
    assert record is not None
    assert record["file_path"] == str(new_path)
    assert record["file_name"] == new_path.name


def test_video_queue_table_widget_drop_ignores_posted_folders(qapp, tmp_path: Path) -> None:
    widget = VideoQueueTableWidget()

    # Create directories:
    # my_folder/
    #   valid1.mp4
    #   _posted/
    #     uploaded.mp4
    #   .posted/
    #     hidden_uploaded.mp4
    #   sub/
    #     valid2.mov
    root = tmp_path / "my_folder"
    root.mkdir()
    (root / "valid1.mp4").write_text("vid1", encoding="utf-8")

    posted_dir = root / "_posted"
    posted_dir.mkdir()
    (posted_dir / "uploaded.mp4").write_text("vid_posted", encoding="utf-8")

    dot_posted_dir = root / ".posted"
    dot_posted_dir.mkdir()
    (dot_posted_dir / "hidden_uploaded.mp4").write_text("vid_dot_posted", encoding="utf-8")

    sub_dir = root / "sub"
    sub_dir.mkdir()
    (sub_dir / "valid2.mov").write_text("vid2", encoding="utf-8")

    # Spy on files_dropped signal
    dropped_files: list[str] = []
    widget.files_dropped.connect(dropped_files.extend)

    # Create synthetic drop event with the root folder URL
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(root))])
    event = MagicMock()
    event.mimeData.return_value = mime_data

    widget.dropEvent(event)
    drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
    event.acceptProposedAction.assert_called_once()

    # Validate that only valid1.mp4 and valid2.mov are collected, ignoring _posted and .posted
    normalized_paths = [Path(p).name for p in dropped_files]
    assert "valid1.mp4" in normalized_paths
    assert "valid2.mov" in normalized_paths
    assert "uploaded.mp4" not in normalized_paths
    assert "hidden_uploaded.mp4" not in normalized_paths
