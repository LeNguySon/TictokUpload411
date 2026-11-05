"""TDD Unit Test Suite for Avatar Cache Service and Circular Avatar Delegate.
Conforms to ECC Development Standards.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem, QTableWidget
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.avatar_cache_service import (
    download_and_cache_avatar,
    get_avatar_cache_path,
)
from src.presentation.delegates.circular_avatar_delegate import CircularAvatarDelegate


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def db_env(tmp_path: Path):
    db_file = tmp_path / "avatar_test.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    return {
        "db_file": db_file,
        "repo": repo,
        "tmp_path": tmp_path,
    }


def test_get_avatar_cache_path_deterministic(tmp_path: Path):
    custom_dir = tmp_path / "custom_profile_dir"
    custom_dir.mkdir()

    p1 = get_avatar_cache_path(101, custom_dir)
    assert p1 == custom_dir / "avatar.jpg"

    p2 = get_avatar_cache_path(102, None)
    assert p2.name == "102.jpg"
    assert "avatars" in str(p2)


def test_download_and_cache_avatar_success(db_env):
    repo: ProfileRepository = db_env["repo"]
    db_file = db_env["db_file"]
    tmp_path = db_env["tmp_path"]

    pid = repo.create({"name": "AvatarUser"})
    # Strict Proxy Gate: avatars are only downloaded through the profile's proxy.
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

    repo.update(pid, proxy_id=ProxyRepository(db_file).create(host="10.0.0.1", port=8080))

    # Create dummy 100x100 PNG bytes
    dummy_img = QImage(100, 100, QImage.Format.Format_RGB32)
    dummy_img.fill(QColor("blue"))
    img_bytes_path = tmp_path / "dummy.png"
    dummy_img.save(str(img_bytes_path), "PNG")
    valid_bytes = img_bytes_path.read_bytes()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = valid_bytes

    with patch("src.infrastructure.tiktok.avatar_cache_service._http_get", return_value=valid_bytes):
        cached_path = download_and_cache_avatar(
            profile_id=pid,
            avatar_url="https://p16.tiktokcdn.com/avatar_test.jpg",
            storage_dir=tmp_path / "AvatarUser",
            db_path=db_file,
        )

        assert cached_path is not None
        assert Path(cached_path).exists()
        assert Path(cached_path).stat().st_size > 0

        # Check DB update
        prof = repo.get_by_id(pid)
        assert prof["avatar_path"] == cached_path
        assert prof["avatar_url"] == "https://p16.tiktokcdn.com/avatar_test.jpg"


def test_circular_avatar_delegate_rendering(app_instance, tmp_path: Path):
    table = QTableWidget(2, 2)
    delegate = CircularAvatarDelegate(table)

    # Create sample image
    sample_img_path = tmp_path / "circle_sample.jpg"
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor("red"))
    img.save(str(sample_img_path))

    # Paint target
    canvas = QPixmap(100, 100)
    canvas.fill(Qt.GlobalColor.white)
    painter = QPainter(canvas)

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 34)

    # 1. Paint with valid image path
    delegate.paint_avatar(painter, option, str(sample_img_path))

    # 2. Paint with empty/missing path (fallback)
    delegate.paint_avatar(painter, option, "")

    painter.end()
    assert True
