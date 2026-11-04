"""TDD Unit Test Suite for Spintax Policy, Channel Update Worker, and Batch Channel Update Dialog.
Conforms to ECC Development Standards.
"""

import random
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.channel_update_worker import ChannelUpdateWorker
from src.domain.policies.spintax_policy import spin_text
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.dialogs.batch_channel_update_dialog import BatchChannelUpdateDialog


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def db_env(tmp_path: Path):
    db_file = tmp_path / "batch_channel_test.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    signal_bus = AppSignalBus.instance()
    return {
        "db_file": db_file,
        "repo": repo,
        "signal_bus": signal_bus,
        "tmp_path": tmp_path,
    }


def test_spintax_policy_flat_and_nested():
    # 1. Flat Spintax
    template_flat = "{Xin chào|Hello|Hi} TikTok"
    res1 = spin_text(template_flat, rng=random.Random(42))
    assert res1 in ["Xin chào TikTok", "Hello TikTok", "Hi TikTok"]

    # 2. Nested Spintax
    template_nested = "{Chào|Hi {bạn|anh em}} #mmo"
    res2 = spin_text(template_nested, rng=random.Random(42))
    assert any(w in res2 for w in ["Chào", "Hi bạn", "Hi anh em"])
    assert "#mmo" in res2


def test_channel_update_worker_updates_profiles(db_env):
    repo: ProfileRepository = db_env["repo"]
    db_file = db_env["db_file"]
    tmp_path = db_env["tmp_path"]

    pid1 = repo.create({"name": "Channel1"})
    pid2 = repo.create({"name": "Channel2"})

    # Create dummy avatar file
    avatar_file = tmp_path / "my_avatar.jpg"
    avatar_file.write_bytes(b"dummy_avatar_data_123456789")

    worker = ChannelUpdateWorker(
        profile_ids=[pid1, pid2],
        db_path=db_file,
        avatar_source=str(avatar_file),
        nickname_pattern="MMO Pro {index}",
        bio_template="{Follow me|Kênh MMO} for updates",
    )

    progress_events = []
    worker.signals.progress.connect(lambda cur, tot, pct: progress_events.append((cur, tot, pct)))

    worker.run()

    assert len(progress_events) == 2

    p1 = repo.get_by_id(pid1)
    p2 = repo.get_by_id(pid2)

    assert p1["nickname"] == "MMO Pro 1"
    assert p2["nickname"] == "MMO Pro 2"
    assert "for updates" in p1["bio"]
    assert "for updates" in p2["bio"]
    assert p1["avatar_path"] == str(avatar_file)
    assert p2["avatar_path"] == str(avatar_file)


def test_batch_channel_update_dialog_ui(app_instance, db_env):
    repo: ProfileRepository = db_env["repo"]
    db_file = db_env["db_file"]

    pid1 = repo.create({"name": "UIChannel1"})
    pid2 = repo.create({"name": "UIChannel2"})

    dialog = BatchChannelUpdateDialog(
        selected_profile_ids=[pid1, pid2],
        profile_repo=repo,
        db_path=db_file,
    )

    assert dialog.profile_count == 2
    assert dialog.chk_avatar.isChecked() is False
    assert dialog.chk_nickname.isChecked() is False
    assert dialog.chk_bio.isChecked() is False

    # Test Spintax Preview button
    dialog.txt_bio.setText("{Chào bạn|Xin chào} kênh của mình")
    dialog._on_preview_spintax()
    preview = dialog.lbl_preview_bio.text()
    assert ("Chào bạn" in preview) or ("Xin chào" in preview)
