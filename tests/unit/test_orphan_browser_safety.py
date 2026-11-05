"""Safety of "Dọn dẹp trình duyệt": only browsers whose --user-data-dir lives inside the app's own
profiles directory may be treated as orphans and terminated.

Previously any chrome/orbita whose command line merely contained the word "profiles" (e.g. the
user's own GoLogin / other antidetect browsers, or the SamMonny daemon's browsers) was killed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.infrastructure.browser import process_supervisor as ps
from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor


class _Proc:
    def __init__(self, pid: int, name: str, cmdline: list[str], create_time: float = 1000.0) -> None:
        self.info = {"pid": pid, "name": name, "cmdline": cmdline, "create_time": create_time}

    def parent(self):
        return None


@pytest.fixture
def fake_psutil(monkeypatch):
    mock = MagicMock()
    mock.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    mock.AccessDenied = type("AccessDenied", (Exception,), {})
    mock.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    monkeypatch.setattr(ps, "psutil", mock)
    return mock


def _scan(fake_psutil, profiles_dir: Path, procs: list[_Proc]) -> set[int]:
    fake_psutil.process_iter.return_value = procs
    supervisor = BrowserProcessSupervisor(profiles_dir=profiles_dir)
    return {o["pid"] for o in supervisor.scan_orphan_browsers(legitimate_pids=set())}


def test_only_browsers_using_our_profiles_dir_are_orphans(fake_psutil, tmp_path: Path):
    ours = tmp_path / "app" / "profiles"
    (ours / "p1").mkdir(parents=True)
    procs = [
        # Real orphan of ours (both CLI spellings, quoted path with spaces)
        _Proc(10, "chrome.exe", ["chrome.exe", f"--user-data-dir={ours / 'p1'}"]),
        _Proc(11, "orbita.exe", ["orbita.exe", "--user-data-dir", f'"{ours / "my profile"}"']),
        # User's own GoLogin browser: path contains "profiles" but is not ours
        _Proc(20, "chrome.exe", ["chrome.exe", r"--user-data-dir=C:\Users\me\.gologin\profiles\abc"]),
        # SamMonny daemon browser (its own profiles dir, managed by the daemon)
        _Proc(21, "orbita.exe", ["orbita.exe", r"--user-data-dir=D:\SamMonny\profiles\uuid-1"]),
        # Sibling directory that merely starts with our path
        _Proc(22, "chrome.exe", ["chrome.exe", f"--user-data-dir={tmp_path / 'app' / 'profiles_backup' / 'x'}"]),
        # "profiles" only appears in another flag
        _Proc(23, "chrome.exe", ["chrome.exe", r"--load-extension=C:\profiles\ext", r"--user-data-dir=C:\Chrome"]),
        # Ordinary Chrome with no --user-data-dir
        _Proc(24, "chrome.exe", ["chrome.exe", "--profile-directory=Default"]),
        # Child (renderer) process of our orphan: dies with its root, never killed directly
        _Proc(25, "chrome.exe", ["chrome.exe", "--type=renderer", f"--user-data-dir={ours / 'p1'}"]),
        # The profiles root itself is not a profile
        _Proc(26, "chrome.exe", ["chrome.exe", f"--user-data-dir={ours}"]),
    ]
    assert _scan(fake_psutil, ours, procs) == {10, 11}


def test_cleanup_skips_pid_reused_by_another_process(fake_psutil, tmp_path: Path):
    proc = MagicMock()
    proc.create_time.return_value = 2000.0  # PID now belongs to a different, newer process
    fake_psutil.Process.return_value = proc

    supervisor = BrowserProcessSupervisor(profiles_dir=tmp_path)
    cleaned = supervisor.cleanup_orphan_browsers(
        orphans=[{"pid": 4242, "name": "chrome.exe", "cmdline": [], "create_time": 1000.0}]
    )

    assert cleaned == []
    proc.terminate.assert_not_called()
    proc.kill.assert_not_called()


def test_cleanup_terminates_matching_orphan(fake_psutil, tmp_path: Path):
    proc = MagicMock()
    proc.create_time.return_value = 1000.0
    fake_psutil.Process.return_value = proc

    supervisor = BrowserProcessSupervisor(profiles_dir=tmp_path)
    cleaned = supervisor.cleanup_orphan_browsers(
        orphans=[{"pid": 4242, "name": "chrome.exe", "cmdline": [], "create_time": 1000.0}]
    )

    assert cleaned == [4242]
    proc.terminate.assert_called_once()
