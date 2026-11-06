"""
Additional coverage tests for src/infrastructure/browser/process_supervisor.py.
Target: raise coverage from 69% to >= 85%.
Tests are hermetic: psutil, ctypes, os.kill are mocked. No real processes are touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import src.infrastructure.browser.process_supervisor as ps_mod
from src.infrastructure.browser.process_supervisor import (
    BrowserProcessSupervisor,
    _is_profile_inside,
    _user_data_dir,
)

# ---------------------------------------------------------------------------
# Module-level helpers: _user_data_dir and _is_profile_inside
# ---------------------------------------------------------------------------

class TestUserDataDir:
    def test_equals_form(self):
        assert _user_data_dir(["chrome.exe", "--user-data-dir=C:/profiles/p1"]) == Path("C:/profiles/p1")

    def test_space_separated_form(self):
        assert _user_data_dir(["chrome.exe", "--user-data-dir", "/home/user/.config/p1"]) == Path("/home/user/.config/p1")

    def test_quoted_path_unquoted(self):
        result = _user_data_dir(['chrome.exe', '--user-data-dir="C:/my profiles/p1"'])
        assert result == Path("C:/my profiles/p1")

    def test_no_user_data_dir_returns_none(self):
        assert _user_data_dir(["chrome.exe", "--type=renderer"]) is None

    def test_empty_cmdline_returns_none(self):
        assert _user_data_dir([]) is None

    def test_user_data_dir_at_end_space_form_missing_value(self):
        """--user-data-dir at the last position with space form = no value -> None."""
        assert _user_data_dir(["chrome.exe", "--user-data-dir"]) is None


class TestIsProfileInside:
    def test_child_dir_is_inside(self, tmp_path):
        root = tmp_path / "profiles"
        child = root / "p1"
        child.mkdir(parents=True)
        assert _is_profile_inside(child, root) is True

    def test_root_itself_is_not_inside(self, tmp_path):
        root = tmp_path / "profiles"
        root.mkdir()
        assert _is_profile_inside(root, root) is False

    def test_sibling_path_prefix_not_inside(self, tmp_path):
        root = tmp_path / "profiles"
        sibling = tmp_path / "profiles_backup" / "p1"
        sibling.mkdir(parents=True)
        assert _is_profile_inside(sibling, root) is False

    def test_unrelated_path_is_not_inside(self, tmp_path):
        root = tmp_path / "profiles"
        unrelated = tmp_path / "other" / "p1"
        unrelated.mkdir(parents=True)
        assert _is_profile_inside(unrelated, root) is False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sup(tmp_path):
    return BrowserProcessSupervisor(profiles_dir=tmp_path / "profiles")


@pytest.fixture
def fake_psutil(monkeypatch):
    mock = MagicMock()
    mock.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    mock.AccessDenied = type("AccessDenied", (Exception,), {})
    mock.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    monkeypatch.setattr(ps_mod, "psutil", mock)
    return mock


# ---------------------------------------------------------------------------
# create_lock
# ---------------------------------------------------------------------------

def test_create_lock_writes_json_with_pid_and_port(sup, tmp_path):
    profile_dir = tmp_path / "profiles" / "p1"
    profile_dir.mkdir(parents=True)

    with patch.object(ps_mod, "psutil", None):
        lock_path = sup.create_lock(profile_dir, pid=1234, port=9222)

    data = json.loads(lock_path.read_text())
    assert data["pid"] == 1234
    assert data["port"] == 9222
    assert "started_at" in data


def test_create_lock_with_psutil_adds_create_time(sup, tmp_path, fake_psutil):
    profile_dir = tmp_path / "profiles" / "p2"
    profile_dir.mkdir(parents=True)

    mock_proc = MagicMock()
    mock_proc.create_time.return_value = 9999999.9
    fake_psutil.Process.return_value = mock_proc

    lock_path = sup.create_lock(profile_dir, pid=5678, port=None)
    data = json.loads(lock_path.read_text())
    assert data.get("process_created_at") == pytest.approx(9999999.9)


def test_create_lock_handles_no_such_process(sup, tmp_path, fake_psutil):
    profile_dir = tmp_path / "profiles" / "p3"
    profile_dir.mkdir(parents=True)

    fake_psutil.Process.side_effect = fake_psutil.NoSuchProcess

    lock_path = sup.create_lock(profile_dir, pid=0, port=None)
    data = json.loads(lock_path.read_text())
    # process_created_at should NOT be in data when NoSuchProcess
    assert "process_created_at" not in data


# ---------------------------------------------------------------------------
# read_lock / is_locked / remove_lock
# ---------------------------------------------------------------------------

def test_read_lock_returns_none_when_no_file(sup, tmp_path):
    assert sup.read_lock(tmp_path / "nonexistent") is None


def test_read_lock_returns_none_on_invalid_json(sup, tmp_path):
    profile_dir = tmp_path / "profiles" / "bad"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text("INVALID JSON }{", encoding="utf-8")
    assert sup.read_lock(profile_dir) is None


def test_is_locked_true_when_file_exists(sup, tmp_path):
    profile_dir = tmp_path / "profiles" / "pl"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text("{}", encoding="utf-8")
    assert sup.is_locked(profile_dir) is True


def test_is_locked_false_when_no_file(sup, tmp_path):
    assert sup.is_locked(tmp_path / "profiles" / "nope") is False


def test_remove_lock_deletes_existing_file(sup, tmp_path):
    profile_dir = tmp_path / "profiles" / "rm"
    profile_dir.mkdir(parents=True)
    lock = profile_dir / ".process.lock"
    lock.write_text("{}")
    sup.remove_lock(profile_dir)
    assert not lock.exists()


def test_remove_lock_ok_when_no_file(sup, tmp_path):
    sup.remove_lock(tmp_path / "profiles" / "none")  # must not raise


# ---------------------------------------------------------------------------
# is_process_running
# ---------------------------------------------------------------------------

def test_is_process_running_no_lock_file(sup, tmp_path):
    assert sup.is_process_running(tmp_path / "profiles" / "noprofile") is False


def test_is_process_running_pid_zero(sup, tmp_path):
    profile_dir = tmp_path / "profiles" / "pid0"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text(json.dumps({"pid": 0}))
    assert sup.is_process_running(profile_dir) is False


def test_is_process_running_plain_int_format_with_psutil(sup, tmp_path, fake_psutil):
    profile_dir = tmp_path / "profiles" / "plain"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text("12345")
    fake_psutil.pid_exists.return_value = True
    assert sup.is_process_running(profile_dir) is True
    fake_psutil.pid_exists.assert_called_once_with(12345)


def test_is_process_running_json_format_pid_not_found(sup, tmp_path, fake_psutil):
    profile_dir = tmp_path / "profiles" / "jnf"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text(json.dumps({"pid": 9999}))
    fake_psutil.pid_exists.return_value = False
    assert sup.is_process_running(profile_dir) is False


def test_is_process_running_without_psutil_uses_os_kill(sup, tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    profile_dir = tmp_path / "profiles" / "oskill"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text(json.dumps({"pid": 11111}))
    with patch("os.kill", return_value=None):
        assert sup.is_process_running(profile_dir) is True


def test_is_process_running_without_psutil_process_not_found(sup, tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    profile_dir = tmp_path / "profiles" / "noproc"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".process.lock").write_text(json.dumps({"pid": 22222}))
    with patch("os.kill", side_effect=ProcessLookupError):
        assert sup.is_process_running(profile_dir) is False


# ---------------------------------------------------------------------------
# scan_orphan_browsers
# ---------------------------------------------------------------------------

def test_scan_orphan_browsers_returns_empty_without_psutil(sup, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    assert sup.scan_orphan_browsers() == []


# ---------------------------------------------------------------------------
# cleanup_orphan_browsers
# ---------------------------------------------------------------------------

def test_cleanup_orphan_browsers_returns_empty_without_psutil(sup, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    # explicit orphans but psutil=None -> empty
    result = sup.cleanup_orphan_browsers(orphans=[{"pid": 100, "name": "chrome.exe", "cmdline": [], "create_time": 1.0}])
    assert result == []


def test_cleanup_orphan_browsers_ignores_invalid_pid_entries(sup, fake_psutil):
    result = sup.cleanup_orphan_browsers(orphans=[{"pid": -1}, {"pid": "bad"}])
    assert result == []


def test_cleanup_orphan_browsers_handles_no_such_process(sup, fake_psutil):
    fake_psutil.Process.side_effect = fake_psutil.NoSuchProcess
    result = sup.cleanup_orphan_browsers(orphans=[{"pid": 100, "name": "chrome.exe", "cmdline": [], "create_time": 1.0}])
    assert 100 in result


def test_cleanup_orphan_browsers_kills_on_timeout(sup, fake_psutil):
    mock_proc = MagicMock()
    mock_proc.create_time.return_value = 1.0
    # First wait raises TimeoutExpired; second wait (after kill) succeeds
    mock_proc.wait.side_effect = [fake_psutil.TimeoutExpired("timed out"), None]
    fake_psutil.Process.return_value = mock_proc

    result = sup.cleanup_orphan_browsers(
        orphans=[{"pid": 200, "name": "chrome.exe", "cmdline": [], "create_time": 1.0}]
    )
    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()
    assert 200 in result


def test_cleanup_orphan_browsers_skips_pid_reused(sup, fake_psutil):
    """If create_time changed (PID reused), process must NOT be killed."""
    mock_proc = MagicMock()
    mock_proc.create_time.return_value = 9999.0  # different from scan time 1.0
    fake_psutil.Process.return_value = mock_proc

    result = sup.cleanup_orphan_browsers(
        orphans=[{"pid": 300, "name": "chrome.exe", "cmdline": [], "create_time": 1.0}]
    )
    mock_proc.terminate.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# shutdown_process_tree
# ---------------------------------------------------------------------------

def test_shutdown_process_tree_invalid_pid_returns_false(sup, fake_psutil):
    assert sup.shutdown_process_tree(-1) is False
    assert sup.shutdown_process_tree(0) is False


def test_shutdown_process_tree_no_such_process_returns_true(sup, fake_psutil):
    fake_psutil.Process.side_effect = fake_psutil.NoSuchProcess
    assert sup.shutdown_process_tree(9999) is True


def test_shutdown_process_tree_terminates_all_children(sup, fake_psutil):
    root_proc = MagicMock()
    child1 = MagicMock()
    child2 = MagicMock()
    root_proc.children.return_value = [child1, child2]
    fake_psutil.Process.return_value = root_proc
    fake_psutil.wait_procs.return_value = ([root_proc, child1, child2], [])  # all gone

    result = sup.shutdown_process_tree(1234)

    assert result is True
    root_proc.terminate.assert_called()
    child1.terminate.assert_called()
    child2.terminate.assert_called()


def test_shutdown_process_tree_kills_alive_after_timeout(sup, fake_psutil):
    root_proc = MagicMock()
    root_proc.children.return_value = []
    fake_psutil.Process.return_value = root_proc
    # First wait_procs: root_proc is alive
    fake_psutil.wait_procs.side_effect = [
        ([], [root_proc]),  # first call: root_proc still alive
        ([root_proc], []),  # second call: finished
    ]

    result = sup.shutdown_process_tree(5678)
    assert result is True
    root_proc.kill.assert_called()


def test_shutdown_process_tree_without_psutil(sup, tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    with patch("os.kill", return_value=None):
        result = sup.shutdown_process_tree(1234)
    assert result is True


def test_shutdown_process_tree_without_psutil_process_not_found(sup, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    with patch("os.kill", side_effect=ProcessLookupError):
        result = sup.shutdown_process_tree(5555)
    assert result is True


# ---------------------------------------------------------------------------
# trim_working_set
# ---------------------------------------------------------------------------

def test_trim_working_set_invalid_pid(sup, fake_psutil):
    result = sup.trim_working_set(-1)
    assert result["success"] is False


def test_trim_working_set_without_psutil(sup, monkeypatch):
    monkeypatch.setattr(ps_mod, "psutil", None)
    result = sup.trim_working_set(1234)
    assert result["success"] is False


def test_trim_working_set_process_not_found(sup, fake_psutil):
    fake_psutil.Process.side_effect = fake_psutil.NoSuchProcess
    result = sup.trim_working_set(9999)
    assert result["success"] is False


def test_trim_working_set_non_windows_skips_win32(sup, fake_psutil, monkeypatch):
    monkeypatch.setattr(ps_mod, "IS_WINDOWS", False)

    mock_proc = MagicMock()
    mock_proc.children.return_value = []
    mock_proc.is_running.return_value = True
    mock_proc.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)
    fake_psutil.Process.return_value = mock_proc

    result = sup.trim_working_set(42)
    # Non-Windows path: returns before Win32 calls, success=False, rss_before_mb populated
    assert result["success"] is False
    assert result["rss_before_mb"] > 0
