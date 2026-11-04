"""
Unit & TDD Test Suite for Browser Lifecycle Management & Safe Cache Cleaning.
Inherited from SamMonny SDK and Gloglin2609 architectures.

Tests:
1. Process lock (.process.lock) lifecycle: create, read, is_locked, remove.
2. Safe cache cleaning: purges Cache, GPUCache, Code Cache, ShaderCache while
   strictly PRESERVING 100% of Cookies, Preferences, Local Storage, and IndexedDB.
3. Orphan browser process detection and cleanup.
4. Working set RAM memory trimming via Win32 EmptyWorkingSet API.
5. OrbitaLauncher lock integration on launch and close.
"""

import json
from pathlib import Path

import pytest
from src.infrastructure.browser.cache_cleaner import (
    PROTECTED_ITEMS,
    BrowserCacheCleaner,
)
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor


@pytest.fixture
def profile_env(tmp_path: Path):
    prof_dir = tmp_path / "test_profile_01"
    prof_dir.mkdir(parents=True, exist_ok=True)

    default_dir = prof_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    # 1. Essential sensitive files (MUST BE PRESERVED)
    cookies_file = default_dir / "Cookies"
    cookies_file.write_text("protected cookie sqlite data", encoding="utf-8")

    pref_file = default_dir / "Preferences"
    pref_file.write_text('{"gologin": {"name": "Test"}}', encoding="utf-8")

    local_storage_dir = default_dir / "Local Storage"
    local_storage_dir.mkdir(parents=True, exist_ok=True)
    (local_storage_dir / "leveldb_data.ldb").write_text("session keys", encoding="utf-8")

    # 2. Cache files & directories (PURGEABLE)
    cache_dir = default_dir / "Cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "data_0").write_text("big video cache chunk 1", encoding="utf-8")

    code_cache_dir = default_dir / "Code Cache" / "js"
    code_cache_dir.mkdir(parents=True, exist_ok=True)
    (code_cache_dir / "script.bin").write_text("compiled script cache", encoding="utf-8")

    gpu_cache_dir = default_dir / "GPUCache"
    gpu_cache_dir.mkdir(parents=True, exist_ok=True)
    (gpu_cache_dir / "data_gpu").write_text("gpu shaders", encoding="utf-8")

    shader_dir = prof_dir / "ShaderCache"
    shader_dir.mkdir(parents=True, exist_ok=True)
    (shader_dir / "gr_shader").write_text("shader data", encoding="utf-8")

    tmp_file = prof_dir / "download_chunk.crdownload"
    tmp_file.write_text("unfinished download", encoding="utf-8")

    return {
        "root": tmp_path,
        "profile_dir": prof_dir,
        "cookies_file": cookies_file,
        "pref_file": pref_file,
        "local_storage_dir": local_storage_dir,
        "cache_dir": cache_dir,
        "code_cache_dir": code_cache_dir,
        "gpu_cache_dir": gpu_cache_dir,
        "shader_dir": shader_dir,
        "tmp_file": tmp_file,
    }


def test_process_lock_lifecycle(tmp_path: Path):
    supervisor = BrowserProcessSupervisor(profiles_dir=tmp_path)
    prof_dir = tmp_path / "prof_lock_test"
    prof_dir.mkdir(parents=True)

    assert not supervisor.is_locked(prof_dir)
    assert supervisor.read_lock(prof_dir) is None

    # Create lock
    lock_file = supervisor.create_lock(prof_dir, pid=4567, port=9222)
    assert lock_file.is_file()
    assert supervisor.is_locked(prof_dir)

    lock_data = supervisor.read_lock(prof_dir)
    assert lock_data is not None
    assert lock_data["pid"] == 4567
    assert lock_data["port"] == 9222
    assert "started_at" in lock_data

    # Remove lock
    supervisor.remove_lock(prof_dir)
    assert not supervisor.is_locked(prof_dir)
    assert supervisor.read_lock(prof_dir) is None


def test_safe_cache_cleaning_purges_cache_preserves_cookies_and_preferences(profile_env):
    prof_dir = profile_env["profile_dir"]
    cleaner = BrowserCacheCleaner()

    # Step 1: Scan
    scan_res = cleaner.scan_cleanable_cache([prof_dir])
    assert scan_res["total_bytes"] > 0
    assert scan_res["profile_cache_dirs_count"] >= 3

    # Step 2: Clean
    clean_res = cleaner.clean_cache([prof_dir])
    assert clean_res["freed_bytes"] > 0
    assert clean_res["deleted_dirs"] >= 3

    # CRITICAL VERIFICATION: Protected items MUST still exist intact!
    assert profile_env["cookies_file"].is_file()
    assert profile_env["cookies_file"].read_text(encoding="utf-8") == "protected cookie sqlite data"

    assert profile_env["pref_file"].is_file()
    assert json.loads(profile_env["pref_file"].read_text(encoding="utf-8"))["gologin"]["name"] == "Test"

    assert profile_env["local_storage_dir"].is_dir()
    assert (profile_env["local_storage_dir"] / "leveldb_data.ldb").is_file()

    # Cache items MUST be deleted
    assert not (prof_dir / "Default" / "Cache").exists()
    assert not (prof_dir / "Default" / "Code Cache").exists()
    assert not (prof_dir / "Default" / "GPUCache").exists()
    assert not (prof_dir / "ShaderCache").exists()
    assert not profile_env["tmp_file"].exists()


def test_protected_items_whitelist_contains_all_critical_keys():
    # Enforce standard invariant: all session, cookie, and extension files are protected
    must_protect = {
        "cookies",
        "preferences",
        "secure preferences",
        "local storage",
        "indexeddb",
        "extensions",
        "login data",
    }
    for item in must_protect:
        assert item in PROTECTED_ITEMS


def test_orphan_browser_scanner_detects_unmanaged_process(tmp_path: Path, monkeypatch):
    supervisor = BrowserProcessSupervisor(profiles_dir=tmp_path)
    prof_dir = tmp_path / "active_prof"
    prof_dir.mkdir()

    # Mock psutil processes:
    # Proc 1: legitimate process active in lock
    # Proc 2: orphan chrome process pointing to prof_dir without active lock
    # Proc 3: unrelated system process (explorer.exe)
    class DummyProc:
        def __init__(self, pid, name, cmdline):
            self.info = {
                "pid": pid,
                "name": name,
                "cmdline": cmdline,
                "create_time": 1000.0,
            }

        def parent(self):
            return None

    fake_processes = [
        DummyProc(101, "chrome.exe", ["chrome.exe", f"--user-data-dir={prof_dir}"]),
        DummyProc(202, "orbita.exe", ["orbita.exe", f"--user-data-dir={tmp_path / 'orphan_prof'}"]),
        DummyProc(303, "explorer.exe", ["explorer.exe"]),
    ]

    import psutil

    monkeypatch.setattr(psutil, "process_iter", lambda _attrs: fake_processes)

    # Active legitimate pid is 101
    orphans = supervisor.scan_orphan_browsers(legitimate_pids={101})

    orphan_pids = [o["pid"] for o in orphans]
    assert 202 in orphan_pids
    assert 101 not in orphan_pids
    assert 303 not in orphan_pids


def test_working_set_memory_trim_safe_execution():
    supervisor = BrowserProcessSupervisor()
    import os

    # Execute on self process
    res = supervisor.trim_working_set(os.getpid())
    assert isinstance(res, dict)
    assert "freed_mb" in res
    assert "rss_before_mb" in res
    assert "rss_after_mb" in res


def test_orbita_launcher_creates_and_removes_process_lock(tmp_path: Path, monkeypatch):
    launcher = OrbitaLauncher(executable_path="C:/Program Files/Orbita/chrome.exe")
    profile_dir = tmp_path / "prof_lock_integrated"

    profile_data = {
        "id": 777,
        "name": "ProfLockIntegrated",
        "storage_dir": str(profile_dir),
    }

    class DummyPopen:
        pid = 9876

        def terminate(self):
            pass

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: DummyPopen())

    # 1. Launch profile -> .process.lock created
    launcher.launch_profile(profile_data)
    supervisor = BrowserProcessSupervisor()
    assert supervisor.is_locked(profile_dir)
    lock_info = supervisor.read_lock(profile_dir)
    assert lock_info["pid"] == 9876

    # 2. Close profile -> .process.lock removed
    launcher.close_profile(777)
    assert not supervisor.is_locked(profile_dir)


def test_main_window_clean_browser_action(qapp, tmp_path, monkeypatch):
    from unittest.mock import patch

    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db_file = tmp_path / "test_mw_clean.db"
    run_all_migrations(db_file)

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    # Trigger _on_clean_browser without crash
    mw._on_clean_browser()
