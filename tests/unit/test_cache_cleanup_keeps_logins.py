"""Cache cleanup (checkbox "Dọn cache tất cả dự án trước khi thoát" + "Dọn dẹp" button), checked on 2026-11-07:

1. it only found 1 of the 17 real browser folders: profiles store a relative ``storage_dir`` ("profiles/<name>") while
   the browser data lives in the daemon's profiles folder (``<daemon>/profiles/<uuid>``): 101.7 MB never cleaned;
2. a browser opened through the daemon writes no ``.process.lock``, so its folder looked idle; the "Dọn dẹp" button did
   not check running browsers at all. Folders used by a running browser (``--user-data-dir``) must be skipped;
3. logins must survive: cookies (browser + database), Local Storage, IndexedDB, Local State (cookie key), Preferences.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.infrastructure.browser import cache_cleaner
from src.infrastructure.browser.cache_cleaner import BrowserCacheCleaner, collect_profile_dirs

LOGIN_FILES = [
    "Local State",
    "Default/Preferences",
    "Default/Secure Preferences",
    "Default/Cookies",
    "Default/Network/Cookies",
    "Default/Network/Cookies-journal",
    "Default/Login Data",
    "Default/Web Data",
    "Default/Local Storage/leveldb/000003.log",
    "Default/Local Storage/leveldb/000004.tmp",  # a leveldb file in use / being written: not "junk"
    "Default/IndexedDB/https_www.tiktok.com_0.indexeddb.leveldb/000005.ldb",
    "Default/Session Storage/000006.log",
]
CACHE_FILES = [
    "Default/Cache/Cache_Data/data_0",
    "Default/Code Cache/js/index",
    "Default/GPUCache/data_1",
    "ShaderCache/data_2",
    "Default/crash_dump.tmp",
]


def _make_profile(root: Path) -> Path:
    for rel in LOGIN_FILES + CACHE_FILES:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(("data:" + rel).encode() * 50)
    return root


def _digest(root: Path) -> dict[str, str]:
    return {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in LOGIN_FILES}


@pytest.fixture
def daemon_dir(tmp_path, monkeypatch):
    base = tmp_path / "daemon_profiles"
    base.mkdir()
    monkeypatch.setattr("src.infrastructure.browser.orbita_launcher.daemon_profiles_dir", lambda: base)
    monkeypatch.setattr(cache_cleaner, "browser_dirs_in_use", lambda: set())
    return base


def test_cleaning_keeps_every_login_file(tmp_path):
    prof = _make_profile(tmp_path / "p")
    before = _digest(prof)
    summary = BrowserCacheCleaner().clean_cache([prof])
    assert _digest(prof) == before
    assert not (prof / "Default/Cache").exists() and not (prof / "Default/crash_dump.tmp").exists()
    assert summary["deleted_dirs"] >= 3


def test_real_daemon_folders_are_found(daemon_dir):
    real = _make_profile(daemon_dir / "1e555ac7-uuid")
    profiles = [
        {"uuid": "1e555ac7-uuid", "name": "swall.pain", "storage_dir": "profiles/swall.pain"},  # relative, missing
        {"uuid": "1e555ac7-uuid", "name": "dup", "storage_dir": str(real)},  # same folder twice
        {"uuid": "no-folder", "name": "x", "storage_dir": "profiles/x"},
    ]
    assert collect_profile_dirs(profiles) == [real]


def test_folders_of_running_browsers_are_skipped(daemon_dir, monkeypatch):
    busy = _make_profile(daemon_dir / "busy")
    idle = _make_profile(daemon_dir / "idle")
    monkeypatch.setattr(cache_cleaner, "browser_dirs_in_use", lambda: {cache_cleaner.normalized_dir(busy)})
    assert collect_profile_dirs([{"uuid": "busy"}, {"uuid": "idle"}]) == [idle]


def test_running_browser_folders_are_read_from_process_command_lines(tmp_path, monkeypatch):
    d = tmp_path / "prof"
    procs = [
        SimpleNamespace(info={"name": "chrome.exe", "cmdline": ["chrome.exe", f"--user-data-dir={d}", "--headless"]}),
        SimpleNamespace(info={"name": "chrome.exe", "cmdline": ["chrome.exe", "--type=renderer"]}),
        SimpleNamespace(info={"name": "notepad.exe", "cmdline": ["notepad.exe", f"--user-data-dir={tmp_path}"]}),
        SimpleNamespace(info={"name": "chrome.exe", "cmdline": None}),
    ]
    fake = SimpleNamespace(process_iter=lambda attrs=None: iter(procs))
    monkeypatch.setattr(cache_cleaner, "psutil", fake)
    assert cache_cleaner.browser_dirs_in_use() == {cache_cleaner.normalized_dir(d)}


def test_exit_cleanup_leaves_database_cookies_untouched(tmp_path, daemon_dir):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db = tmp_path / "app.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "acc", "uuid": "acc-uuid", "cookies_json": "sessionid=abc; sid_tt=def"})
    repo.update(pid, cookies_browser='[{"name":"sessionid","value":"abc"}]')
    prof = _make_profile(daemon_dir / "acc-uuid")
    before_db = {k: repo.get_by_id(pid)[k] for k in ("cookies_json", "cookies_browser", "status")}
    before_files = _digest(prof)

    fake_window = SimpleNamespace(profile_repo=repo, hide=lambda: None)
    TikTokManagerMainWindow._clean_cache_on_exit(fake_window)

    assert {k: repo.get_by_id(pid)[k] for k in before_db} == before_db
    assert _digest(prof) == before_files
    assert not (prof / "Default/Cache").exists()  # it really cleaned the real folder


def test_clean_button_skips_running_browsers(tmp_path, daemon_dir, monkeypatch):
    """The "Dọn dẹp" button used the same folder list without any running check."""
    from src.presentation.views.main_window import TikTokManagerMainWindow

    busy = _make_profile(daemon_dir / "busy")
    monkeypatch.setattr(cache_cleaner, "browser_dirs_in_use", lambda: {cache_cleaner.normalized_dir(busy)})
    repo = SimpleNamespace(list_all=lambda: [{"uuid": "busy"}])
    tasks = []
    fake = SimpleNamespace(profile_repo=repo, _run_bg=lambda fn, *a, **k: tasks.append(fn), _on_browser_cleaned=None)
    with patch("src.presentation.views.main_window.InfoBar"):
        TikTokManagerMainWindow._on_clean_browser(fake)
    assert tasks
    tasks[0]()
    assert (busy / "Default/Cache").exists()
