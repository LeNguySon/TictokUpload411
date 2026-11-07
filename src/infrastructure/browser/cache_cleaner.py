"""
Browser Cache & Disk Cleaner Engine.
Purges browser cache directories, GPU shader cache, and temporary download artifacts
while strictly preserving 100% of user cookies, preferences, and session tokens.
Inherited from Gloglin2609 and SamMonny SDK standards.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ships with the app
    psutil = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Cache subdirectories relative to profile storage root that can be safely purged
PURGEABLE_CACHE_DIRS: list[Path] = [
    Path("Default") / "Cache",
    Path("Default") / "Code Cache",
    Path("Default") / "GPUCache",
    Path("Default") / "Service Worker" / "CacheStorage",
    Path("Default") / "Service Worker" / "ScriptCache",
    Path("Default") / "Crashpad" / "reports",
    Path("ShaderCache"),
    Path("GrShaderCache"),
]

# Sensitive items that MUST NEVER BE DELETED under any circumstances
PROTECTED_ITEMS: set[str] = {
    "preferences",
    "secure preferences",
    "cookies",
    "cookies-journal",
    "local state",
    "local storage",
    "indexeddb",
    "extension state",
    "extensions",
    "history",
    "web data",
    "login data",
    "avatar.jpg",
    "custom_flags.json",
    ".process.lock",
}

# Folders holding login/session state: nothing inside them is ever deleted (not even "*.tmp": LevelDB/SQLite write
# temporary files there while the profile is in use).
PROTECTED_DIRS: set[str] = {
    "network",
    "local storage",
    "session storage",
    "indexeddb",
    "databases",
    "storage",
    "shared_proto_db",
    "extension state",
    "extensions",
    "sync data",
}

_BROWSER_PROCESS_NAMES = ("chrome", "orbita", "chromium")


def format_bytes(bytes_count: int | float) -> str:
    """Formats bytes count to human-readable string (KB, MB, GB)."""
    if bytes_count < 1024:
        return f"{int(bytes_count)} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except (OSError, PermissionError):
        return 0


def _get_dir_size(path: Path) -> int:
    """Calculates directory size recursively."""
    total = 0
    if not path.exists() or not path.is_dir():
        return 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += _safe_file_size(entry)
    except (OSError, PermissionError):
        pass
    return total


class BrowserCacheCleaner:
    """Safe, non-blocking browser cache cleaner with strict credential preservation."""

    def scan_cleanable_cache(self, profile_dirs: list[Path]) -> dict[str, Any]:
        """
        Inspects given profile directories and returns cleanable items summary
        with estimated space savings.
        """
        result: dict[str, Any] = {
            "total_bytes": 0,
            "tmp_files_count": 0,
            "tmp_files_bytes": 0,
            "profile_cache_dirs_count": 0,
            "profile_cache_bytes": 0,
            "items_to_clean": [],
        }

        for prof_dir in profile_dirs:
            p_dir = Path(prof_dir).resolve()
            if not p_dir.is_dir():
                continue

            # 1. Scan purgeable cache directories
            for rel_cache in PURGEABLE_CACHE_DIRS:
                target = p_dir / rel_cache
                if target.exists() and target.is_dir():
                    dir_size = _get_dir_size(target)
                    if dir_size > 0:
                        result["profile_cache_dirs_count"] += 1
                        result["profile_cache_bytes"] += dir_size
                        result["items_to_clean"].append(
                            {
                                "path": target,
                                "type": "dir",
                                "size": dir_size,
                            }
                        )

            # 2. Scan temporary dangling files (*.tmp, *.crdownload, *.part)
            for ext in ("*.tmp", "*.crdownload", "*.part"):
                for tmp_file in p_dir.rglob(ext):
                    rel_parts = {part.lower() for part in tmp_file.relative_to(p_dir).parts[:-1]}
                    if rel_parts & PROTECTED_DIRS:
                        continue  # session storage (Local Storage, IndexedDB, cookies...): never touched
                    if tmp_file.is_file():
                        size = _safe_file_size(tmp_file)
                        result["tmp_files_count"] += 1
                        result["tmp_files_bytes"] += size
                        result["items_to_clean"].append(
                            {
                                "path": tmp_file,
                                "type": "file",
                                "size": size,
                            }
                        )

        result["total_bytes"] = result["profile_cache_bytes"] + result["tmp_files_bytes"]
        result["formatted_total"] = format_bytes(result["total_bytes"])
        return result

    def clean_cache(
        self,
        profile_dirs: list[Path],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Safely deletes cleanable cache directories and files without touching
        any protected session, cookie, or extension data.
        """
        scan = self.scan_cleanable_cache(profile_dirs)
        items = scan["items_to_clean"]
        total_items = len(items)

        freed_bytes = 0
        deleted_files = 0
        deleted_dirs = 0
        failed_items = 0

        for idx, item in enumerate(items, 1):
            path: Path = item["path"]
            item_type: str = item["type"]
            expected_size: int = item["size"]

            # Double check against protected items whitelist
            if path.name.lower() in PROTECTED_ITEMS:
                continue

            if progress_callback:
                progress_callback(idx, total_items, f"Đang dọn dẹp: {path.name}")

            try:
                if item_type == "file" and path.exists() and path.is_file():
                    actual_size = _safe_file_size(path)
                    path.unlink(missing_ok=True)
                    freed_bytes += actual_size or expected_size
                    deleted_files += 1
                elif item_type == "dir" and path.exists() and path.is_dir():
                    actual_size = _get_dir_size(path)
                    shutil.rmtree(path, ignore_errors=True)
                    freed_bytes += actual_size or expected_size
                    deleted_dirs += 1
            except Exception as exc:
                failed_items += 1
                logger.warning("Could not delete %s during cache cleanup: %s", path, exc)

        summary = {
            "freed_bytes": freed_bytes,
            "formatted_freed": format_bytes(freed_bytes),
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs,
            "failed_items": failed_items,
        }
        logger.info(
            "Cache cleanup completed: Freed %s (%d files, %d dirs)",
            summary["formatted_freed"],
            deleted_files,
            deleted_dirs,
        )
        return summary


def normalized_dir(path: str | Path) -> str:
    """Comparable form of a folder path (absolute, case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(str(path)))


def browser_dirs_in_use() -> set[str]:
    """``--user-data-dir`` of every running Chrome/Orbita browser (renderers/helpers excluded).

    Browsers started through the SamMonny daemon write no ``.process.lock``: their command line is the only reliable
    sign that a profile folder is in use.
    """
    if psutil is None:
        return set()
    in_use: set[str] = set()
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            cmdline = proc.info.get("cmdline") or []
        except Exception:
            continue
        if not any(b in name for b in _BROWSER_PROCESS_NAMES):
            continue
        for arg in cmdline:
            if arg.startswith("--user-data-dir="):
                in_use.add(normalized_dir(arg.split("=", 1)[1].strip('"')))
    return in_use


def collect_profile_dirs(profiles: list[dict[str, Any]], skip_in_use: bool = True) -> list[Path]:
    """Existing browser folders of the given profiles (the daemon's ``profiles/<uuid>`` included), each once.

    ``storage_dir`` is often a relative ``profiles/<name>`` that does not exist: the data lives in the daemon's
    profiles folder (only 1 of 17 real folders used to be found). With ``skip_in_use`` folders of running browsers
    (``.process.lock`` or a live ``--user-data-dir``) are left alone.
    """
    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
    from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor

    in_use = browser_dirs_in_use() if skip_in_use else set()
    supervisor = BrowserProcessSupervisor() if skip_in_use else None
    seen: set[str] = set()
    dirs: list[Path] = []
    for p in profiles:
        found = OrbitaLauncher.locate_profile_dir(p)
        if found is None or not found.is_dir():
            continue
        key = normalized_dir(found)
        if key in seen:
            continue
        seen.add(key)
        if skip_in_use and (key in in_use or (supervisor is not None and supervisor.is_process_running(found))):
            logger.info("Cache cleanup skips %s: its browser is running", found)
            continue
        dirs.append(found)
    return dirs
