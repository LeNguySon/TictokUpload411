"""
Additional coverage tests for src/infrastructure/browser/sammonny_daemon_manager.py.
Target: raise coverage from 53% to >= 85%.
Tests are hermetic: subprocess, urllib, time.sleep, and engine_paths are fully mocked.
Real sammonny-daemon.exe is never launched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _healthy_response(data: dict | None = None, code: int = 200) -> MagicMock:
    """Return a mock urllib response object that yields JSON."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.getcode.return_value = code
    resp.read.return_value = json.dumps(data or {"status": "ok"}).encode()
    return resp


@pytest.fixture
def supervisor():
    """SamMonnyDaemonSupervisor with atexit disabled (avoid polluting real atexit stack)."""
    return SamMonnyDaemonSupervisor(
        internal_port=7654, sdk_port=36912, auto_register_atexit=False
    )


# ---------------------------------------------------------------------------
# __init__ — atexit registration
# ---------------------------------------------------------------------------

def test_init_registers_atexit_by_default():
    registered = []
    with patch("atexit.register", side_effect=lambda fn: registered.append(fn)):
        sup = SamMonnyDaemonSupervisor(auto_register_atexit=True)
    assert sup.shutdown in registered


def test_init_skips_atexit_when_disabled():
    with patch("atexit.register") as mock_reg:
        SamMonnyDaemonSupervisor(auto_register_atexit=False)
    mock_reg.assert_not_called()


# ---------------------------------------------------------------------------
# find_daemon_binary
# ---------------------------------------------------------------------------

def test_find_daemon_binary_returns_none_when_not_found(supervisor, tmp_path):
    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.daemon_binary_candidates",
        return_value=[tmp_path / "nonexistent.exe"],
    ):
        result = supervisor.find_daemon_binary()
    assert result is None


def test_find_daemon_binary_returns_first_existing(supervisor, tmp_path):
    real_bin = tmp_path / "sammonny-daemon.exe"
    real_bin.write_bytes(b"MZ")  # fake PE header
    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.daemon_binary_candidates",
        return_value=[tmp_path / "missing.exe", real_bin],
    ):
        result = supervisor.find_daemon_binary()
    assert result == real_bin


# ---------------------------------------------------------------------------
# find_working_dir
# ---------------------------------------------------------------------------

def test_find_working_dir_returns_first_existing_dir(supervisor, tmp_path):
    real_root = tmp_path / "sammonny_root"
    real_root.mkdir()
    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.sammonny_roots",
        return_value=[tmp_path / "missing_root", real_root],
    ):
        result = supervisor.find_working_dir()
    assert result == real_root


def test_find_working_dir_falls_back_to_cwd_when_none_exists(supervisor, tmp_path):
    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.sammonny_roots",
        return_value=[tmp_path / "missing_a", tmp_path / "missing_b"],
    ):
        result = supervisor.find_working_dir()
    assert result == Path.cwd()


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

def test_check_health_both_ports_up(supervisor):
    healthy_7654 = _healthy_response({"status": "ok"})
    healthy_36912 = _healthy_response()

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "7654" in url:
            return healthy_7654
        return healthy_36912

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = supervisor.check_health()

    assert result["daemon_7654"] is True
    assert result["sdk_36912"] is True


def test_check_health_both_ports_down(supervisor):
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = supervisor.check_health()
    assert result["daemon_7654"] is False
    assert result["sdk_36912"] is False


def test_check_health_daemon_up_sdk_down(supervisor):
    healthy_7654 = _healthy_response({"status": "ok"})

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "7654" in url:
            return healthy_7654
        raise OSError("sdk port down")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = supervisor.check_health()

    assert result["daemon_7654"] is True
    assert result["sdk_36912"] is False


def test_check_health_sdk_up_daemon_down(supervisor):
    healthy_36912 = _healthy_response()

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "36912" in url:
            return healthy_36912
        raise OSError("7654 port down")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = supervisor.check_health()

    assert result["daemon_7654"] is False
    assert result["sdk_36912"] is True


def test_check_health_non_200_response(supervisor):
    bad_resp = MagicMock()
    bad_resp.__enter__ = lambda s: s
    bad_resp.__exit__ = MagicMock(return_value=False)
    bad_resp.getcode.return_value = 503

    with patch("urllib.request.urlopen", return_value=bad_resp):
        result = supervisor.check_health()

    assert result["daemon_7654"] is False
    assert result["sdk_36912"] is False


# ---------------------------------------------------------------------------
# is_running
# ---------------------------------------------------------------------------

def test_is_running_true_when_daemon_7654_up(supervisor):
    with patch.object(supervisor, "check_health", return_value={"daemon_7654": True, "sdk_36912": False}):
        assert supervisor.is_running() is True


def test_is_running_true_when_sdk_36912_up(supervisor):
    with patch.object(supervisor, "check_health", return_value={"daemon_7654": False, "sdk_36912": True}):
        assert supervisor.is_running() is True


def test_is_running_false_when_both_down(supervisor):
    with patch.object(supervisor, "check_health", return_value={"daemon_7654": False, "sdk_36912": False}):
        assert supervisor.is_running() is False


# ---------------------------------------------------------------------------
# ensure_daemon_running
# ---------------------------------------------------------------------------

def test_ensure_daemon_running_already_running(supervisor):
    with patch.object(supervisor, "is_running", return_value=True):
        result = supervisor.ensure_daemon_running()
    assert result is True


def test_ensure_daemon_running_binary_not_found(supervisor):
    with (
        patch.object(supervisor, "is_running", return_value=False),
        patch.object(supervisor, "find_daemon_binary", return_value=None),
    ):
        result = supervisor.ensure_daemon_running()
    assert result is False


def test_ensure_daemon_running_spawn_success(supervisor, tmp_path):
    fake_bin = tmp_path / "sammonny-daemon.exe"
    fake_bin.write_bytes(b"MZ")

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    # is_running: False first (triggers spawn), then True after spawn
    is_running_values = [False, False, True]
    is_running_iter = iter(is_running_values)

    def fake_is_running():
        return next(is_running_iter, True)

    with (
        patch.object(supervisor, "is_running", side_effect=fake_is_running),
        patch.object(supervisor, "find_daemon_binary", return_value=fake_bin),
        patch.object(supervisor, "find_working_dir", return_value=tmp_path),
        patch("subprocess.Popen", return_value=mock_proc),
        patch("time.sleep"),
    ):
        result = supervisor.ensure_daemon_running(timeout_sec=2.0)

    assert result is True
    assert supervisor._spawned_process is mock_proc


def test_ensure_daemon_running_spawn_popen_fails(supervisor, tmp_path):
    fake_bin = tmp_path / "sammonny-daemon.exe"
    fake_bin.write_bytes(b"MZ")

    with (
        patch.object(supervisor, "is_running", return_value=False),
        patch.object(supervisor, "find_daemon_binary", return_value=fake_bin),
        patch.object(supervisor, "find_working_dir", return_value=tmp_path),
        patch("subprocess.Popen", side_effect=OSError("access denied")),
    ):
        result = supervisor.ensure_daemon_running(timeout_sec=0.1)

    assert result is False


def test_ensure_daemon_running_timeout(supervisor, tmp_path):
    """Daemon never becomes healthy -> timeout -> returns False.

    We mock time.time only inside the sammonny_daemon_manager module so that
    the logging framework (which also calls time.time()) is unaffected.
    """
    fake_bin = tmp_path / "sammonny-daemon.exe"
    fake_bin.write_bytes(b"MZ")
    mock_proc = MagicMock()

    # Provide enough values: start_time=0.0, then loop check always returns 100.0 (> timeout)
    with (
        patch.object(supervisor, "is_running", return_value=False),
        patch.object(supervisor, "find_daemon_binary", return_value=fake_bin),
        patch.object(supervisor, "find_working_dir", return_value=tmp_path),
        patch("subprocess.Popen", return_value=mock_proc),
        patch("time.sleep"),
        patch(
            "src.infrastructure.browser.sammonny_daemon_manager.time.time",
            side_effect=[0.0] + [100.0] * 20,
        ),
    ):
        result = supervisor.ensure_daemon_running(timeout_sec=0.001)

    assert result is False


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------

def test_shutdown_no_process_is_noop(supervisor):
    supervisor._spawned_process = None
    supervisor.shutdown()  # must not raise


def test_shutdown_terminates_spawned_process(supervisor):
    mock_proc = MagicMock()
    mock_proc.pid = 9999
    supervisor._spawned_process = mock_proc

    supervisor.shutdown()

    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once()
    assert supervisor._spawned_process is None


def test_shutdown_kills_if_terminate_fails(supervisor):
    mock_proc = MagicMock()
    mock_proc.pid = 8888
    mock_proc.terminate.side_effect = OSError("terminate failed")
    supervisor._spawned_process = mock_proc

    supervisor.shutdown()

    mock_proc.kill.assert_called_once()
    assert supervisor._spawned_process is None


def test_shutdown_handles_kill_exception_gracefully(supervisor):
    mock_proc = MagicMock()
    mock_proc.pid = 7777
    mock_proc.terminate.side_effect = OSError("terminate failed")
    mock_proc.kill.side_effect = OSError("kill also failed")
    supervisor._spawned_process = mock_proc

    supervisor.shutdown()  # must not raise

    assert supervisor._spawned_process is None
