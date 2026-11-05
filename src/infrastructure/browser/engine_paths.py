"""
Discovery of browser engines and SamMonny daemon locations without machine-specific paths.

Resolution order for every location:
1. Environment variable (per-machine configuration).
2. Discovery under known roots derived from the current user / repo (no hard-coded user name).
3. Legacy defaults used before this module existed (kept so existing setups keep working).

Orbita: the engine folder with the highest version number wins (orbita-152 > orbita-139), so
installing a newer engine is picked up without code changes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ORBITA_PATH_ENV = "TAVM_ORBITA_PATH"  # explicit chrome.exe
ORBITA_ENGINES_ENV = "TAVM_ORBITA_ENGINES_DIR"  # one or more dirs (os.pathsep) holding orbita-<N>/
DAEMON_PROFILES_ENV = "TAVM_DAEMON_PROFILES_DIR"
DAEMON_BINARY_ENV = "TAVM_SAMMONNY_DAEMON"
SAMMONNY_ROOT_ENV = "TAVM_SAMMONNY_ROOT"

_ENGINE_DIR_RE = re.compile(r"^orbita(?:-browser)?-(\d+)$", re.IGNORECASE)

# Legacy defaults (previously hard-coded); only used when nothing configured/discovered.
_LEGACY_SAMMONNY_ROOTS = (
    Path(r"D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker"),
    Path(r"D:\SamMonnygocLiengXiPoker"),
)
_SYSTEM_BROWSERS = (
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    return [Path(p) for p in raw.split(os.pathsep) if p.strip()]


def _user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def orbita_engine_roots() -> list[Path]:
    """Directories that contain versioned engine folders (orbita-<N>/chrome.exe)."""
    home = _user_home()
    return [
        *_env_paths(ORBITA_ENGINES_ENV),
        home / "Desktop" / "Gloglin2609" / "resources" / "engines",
        home / ".gologin" / "browser",
        *(root / "resources" / "engines" for root in sammonny_roots()),
    ]


def engine_version(executable: Path) -> int | None:
    match = _ENGINE_DIR_RE.match(executable.parent.name)
    return int(match.group(1)) if match else None


def discover_orbita_executable() -> Path | None:
    """Explicit env path, else the newest orbita-<N>/chrome.exe under the engine roots, else system Chrome/Edge."""
    for explicit in _env_paths(ORBITA_PATH_ENV):
        if explicit.is_file():
            return explicit

    candidates: list[tuple[int, Path]] = []
    for root in orbita_engine_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            exe = child / "chrome.exe"
            version = engine_version(exe)
            if version is not None and exe.is_file():
                candidates.append((version, exe))
    if candidates:
        return max(candidates, key=lambda c: c[0])[1]

    for browser in _SYSTEM_BROWSERS:
        if browser.is_file():
            return browser
    return None


def sammonny_roots() -> list[Path]:
    """SamMonny installation/repo roots (env first, then legacy locations)."""
    return [*_env_paths(SAMMONNY_ROOT_ENV), *_LEGACY_SAMMONNY_ROOTS]


def daemon_profiles_dir() -> Path:
    """Profiles directory managed by the SamMonny daemon."""
    env = _env_paths(DAEMON_PROFILES_ENV)
    if env:
        return env[0]
    for root in sammonny_roots():
        candidate = root / "profiles"
        if candidate.is_dir():
            return candidate
    return _LEGACY_SAMMONNY_ROOTS[0] / "profiles"


def daemon_binary_candidates() -> list[Path]:
    """Possible sammonny-daemon.exe locations (env first)."""
    rel = Path("dist_standalone") / "sammonny-antidetect" / "bin" / "sammonny-daemon.exe"
    return [
        *_env_paths(DAEMON_BINARY_ENV),
        *(root / rel for root in sammonny_roots()),
        Path(r"C:\SamMonny\bin\sammonny-daemon.exe"),
    ]
