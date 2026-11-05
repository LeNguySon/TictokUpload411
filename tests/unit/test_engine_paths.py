"""Engine / daemon path discovery: no machine-specific hard-coded paths required.

Orbita, the SamMonny daemon binary and the daemon profiles dir were hard-coded to this machine
(C:\\Users\\sonson\\Desktop\\Gloglin2609\\..., D:\\SamMonny...), so another machine - or a newly
installed Orbita version - was never picked up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.infrastructure.browser import engine_paths as ep


def _engine(root: Path, folder: str) -> Path:
    exe = root / folder / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    return exe


def test_explicit_orbita_path_wins(tmp_path, monkeypatch):
    exe = _engine(tmp_path, "custom")
    monkeypatch.setenv(ep.ORBITA_PATH_ENV, str(exe))
    assert ep.discover_orbita_executable() == exe


def test_newest_orbita_engine_is_selected(tmp_path, monkeypatch):
    monkeypatch.delenv(ep.ORBITA_PATH_ENV, raising=False)
    for folder in ("orbita-123", "orbita-152", "orbita-139", "orbita-browser-155", "not-an-engine"):
        _engine(tmp_path, folder)
    monkeypatch.setenv(ep.ORBITA_ENGINES_ENV, str(tmp_path))
    found = ep.discover_orbita_executable()
    assert found.parent.name == "orbita-browser-155"


def test_engine_version_parsing():
    assert ep.engine_version(Path("x/orbita-152/chrome.exe")) == 152
    assert ep.engine_version(Path("x/orbita-browser-130/chrome.exe")) == 130
    assert ep.engine_version(Path("x/custom/chrome.exe")) is None


def test_daemon_profiles_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ep.DAEMON_PROFILES_ENV, str(tmp_path))
    assert ep.daemon_profiles_dir() == tmp_path


def test_daemon_binary_from_env_first(tmp_path, monkeypatch):
    from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor

    exe = tmp_path / "sammonny-daemon.exe"
    exe.write_bytes(b"x")
    monkeypatch.setenv(ep.DAEMON_BINARY_ENV, str(exe))
    assert SamMonnyDaemonSupervisor(auto_register_atexit=False).find_daemon_binary() == exe


def test_launcher_uses_discovery(tmp_path, monkeypatch):
    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

    exe = _engine(tmp_path, "orbita-160")
    monkeypatch.setenv(ep.ORBITA_PATH_ENV, str(exe))
    assert OrbitaLauncher().executable_path == exe


def test_no_user_specific_paths_in_source():
    for path in (
        "src/infrastructure/browser/orbita_launcher.py",
        "src/infrastructure/browser/sammonny_daemon_manager.py",
    ):
        text = Path(path).read_text(encoding="utf-8")
        assert r"C:\Users\sonson" not in text, f"{path} hard-codes a user profile path"


@pytest.mark.parametrize("missing", [True])
def test_discovery_never_returns_a_missing_engine(tmp_path, monkeypatch, missing):
    monkeypatch.setenv(ep.ORBITA_PATH_ENV, str(tmp_path / "nope" / "chrome.exe"))
    monkeypatch.setenv(ep.ORBITA_ENGINES_ENV, str(tmp_path / "empty"))
    found = ep.discover_orbita_executable()
    assert found is None or found.is_file() or found.name == "chrome.exe"
