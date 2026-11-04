"""
Browser Process Supervisor & Lifecycle Engine.
Manages profile locks, process tree shutdown, orphan/zombie process sweeping,
and Win32 EmptyWorkingSet working set memory trimming.
Inherited from SamMonny SDK and Gloglin2609 architectures.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
DEFAULT_PROFILES_DIR = Path("profiles")
PROCESS_LOCK_FILENAME = ".process.lock"

# Win32 Process Access Rights for EmptyWorkingSet
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_TRIM_ACCESS = _PROCESS_SET_QUOTA | _PROCESS_QUERY_INFORMATION


class BrowserProcessSupervisor:
    """Manages profile processes, detects zombies/orphans, and enforces zero-leak lifecycle."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self.profiles_dir = Path(profiles_dir or DEFAULT_PROFILES_DIR).resolve()

    def _lock_path(self, profile_dir: Path) -> Path:
        return Path(profile_dir) / PROCESS_LOCK_FILENAME

    def create_lock(self, profile_dir: Path, pid: int, port: int | None = None) -> Path:
        """Creates a lock file tying a live browser process to a profile directory."""
        path = self._lock_path(profile_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "pid": pid,
            "port": port,
            "started_at": datetime.now(UTC).isoformat(),
        }
        if psutil is not None:
            try:
                data["process_created_at"] = psutil.Process(pid).create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def read_lock(self, profile_dir: Path) -> dict[str, Any] | None:
        """Reads lock file data if present and valid."""
        path = self._lock_path(profile_dir)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("Failed reading lock %s: %s", path, e)
            return None

    def is_locked(self, profile_dir: Path) -> bool:
        """Checks if a lock file exists for the profile directory."""
        return self._lock_path(profile_dir).is_file()

    def is_process_running(self, profile_dir: Path) -> bool:
        """
        Checks if the process associated with profile_dir is currently alive in the OS.
        Inspects .process.lock (supports JSON dict with 'pid' or plain PID integer).
        """
        path = self._lock_path(profile_dir)
        if not path.is_file():
            return False

        try:
            raw_text = path.read_text(encoding="utf-8").strip()
            pid: int | None = None
            if raw_text.startswith("{"):
                data = json.loads(raw_text)
                pid = data.get("pid")
            elif raw_text.isdigit():
                pid = int(raw_text)

            if not pid or pid <= 0:
                return False

            if psutil is not None:
                return psutil.pid_exists(pid)
            else:
                try:
                    os.kill(pid, 0)
                    return True
                except (OSError, ProcessLookupError):
                    return False
        except Exception as e:
            logger.debug("Failed checking is_process_running for %s: %s", profile_dir, e)
            return False

    def remove_lock(self, profile_dir: Path) -> None:
        """Removes the process lock file."""
        try:
            self._lock_path(profile_dir).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not remove lock for %s: %s", profile_dir, e)

    def scan_orphan_browsers(
        self,
        profiles_dir: Path | None = None,
        legitimate_pids: Iterable[int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scans OS for orphaned Chrome/Orbita instances.
        An orphan is an orbita/chrome process running with --user-data-dir targeting
        our profiles directory, but neither active in a lock file nor belonging to active PIDs.
        """
        if psutil is None:
            return []

        target_dir = Path(profiles_dir or self.profiles_dir).resolve()
        target_dir_str = str(target_dir).casefold()

        active_legitimate: set[int] = set(legitimate_pids or ())

        # Collect active PIDs from lock files across profile folders
        if legitimate_pids is None and target_dir.exists():
            for child in target_dir.iterdir():
                if child.is_dir():
                    lock = self.read_lock(child)
                    if lock and isinstance(lock.get("pid"), int) and lock["pid"] > 0:
                        active_legitimate.add(lock["pid"])

        orphans: list[dict[str, Any]] = []

        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                pid = proc.info.get("pid")
                if not pid or pid in active_legitimate:
                    continue

                name = (proc.info.get("name") or "").casefold()
                if not ("chrome" in name or "orbita" in name):
                    continue

                cmdline_list = proc.info.get("cmdline") or []
                cmdline = " ".join(cmdline_list).casefold()

                # Target only processes using our profile storage path
                if target_dir_str not in cmdline and "profiles" not in cmdline:
                    continue

                # Verify if process is descendant of any legitimate active root
                is_child_of_legitimate = False
                cur = proc
                visited = 0
                while cur and visited < 10:
                    visited += 1
                    try:
                        parent = cur.parent()
                        if not parent:
                            break
                        if parent.pid in active_legitimate:
                            is_child_of_legitimate = True
                            break
                        cur = parent
                    except Exception:
                        break

                if is_child_of_legitimate:
                    continue

                orphans.append(
                    {
                        "pid": pid,
                        "name": proc.info.get("name"),
                        "cmdline": cmdline_list,
                        "create_time": proc.info.get("create_time"),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return orphans

    def cleanup_orphan_browsers(
        self,
        orphans: list[dict[str, Any]] | None = None,
        profiles_dir: Path | None = None,
    ) -> list[int]:
        """Terminates orphaned browser processes cleanly without leaving zombies."""
        if orphans is None:
            orphans = self.scan_orphan_browsers(profiles_dir=profiles_dir)

        if not orphans or psutil is None:
            return []

        cleaned_pids: list[int] = []
        for item in orphans:
            pid = item.get("pid")
            if not isinstance(pid, int) or pid <= 0:
                continue
            try:
                proc = psutil.Process(pid)
                logger.warning("Sweeping orphan browser PID %s (%s)", pid, item.get("name"))
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1.0)
                cleaned_pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cleaned_pids.append(pid)
            except Exception as exc:
                logger.error("Failed terminating orphan PID %s: %s", pid, exc)

        return cleaned_pids

    def shutdown_process_tree(self, pid: int, timeout: float = 3.0) -> bool:
        """Gracefully terminates root process and all recursive children (GPU, renderer, etc)."""
        if not isinstance(pid, int) or pid <= 0:
            return False

        if psutil is None:
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return True
            except Exception:
                return False

        try:
            root = psutil.Process(pid)
            tree = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True

        for proc in tree:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Wait for tree exit
        gone, alive = psutil.wait_procs(tree, timeout=timeout)
        if alive:
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
            psutil.wait_procs(alive, timeout=1.0)

        return True

    def trim_working_set(self, root_pid: int) -> dict[str, Any]:
        """
        Releases unreferenced physical RAM pages back to Windows OS via EmptyWorkingSet.
        Safe: Does NOT terminate processes or drop network connections.
        """
        result: dict[str, Any] = {
            "root_pid": root_pid,
            "success": False,
            "processes_trimmed": 0,
            "rss_before_mb": 0.0,
            "rss_after_mb": 0.0,
            "freed_mb": 0.0,
        }

        if psutil is None or not isinstance(root_pid, int) or root_pid <= 0:
            return result

        try:
            root = psutil.Process(root_pid)
            tree = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return result

        total_rss_before = sum(p.memory_info().rss for p in tree if p.is_running())
        rss_before_mb = round(total_rss_before / (1024 * 1024), 2)
        result["rss_before_mb"] = rss_before_mb

        if not IS_WINDOWS:
            return result

        trimmed_count = 0
        try:
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi

            for proc in tree:
                handle = None
                try:
                    handle = kernel32.OpenProcess(_PROCESS_TRIM_ACCESS, False, proc.pid)
                    if handle:
                        if psapi.EmptyWorkingSet(handle) != 0:
                            trimmed_count += 1
                except Exception:
                    pass
                finally:
                    if handle:
                        kernel32.CloseHandle(handle)
        except Exception as e:
            logger.debug("Win32 EmptyWorkingSet error: %s", e)

        time.sleep(0.05)
        total_rss_after = sum(p.memory_info().rss for p in tree if p.is_running())
        rss_after_mb = round(total_rss_after / (1024 * 1024), 2)
        freed_mb = max(0.0, round(rss_before_mb - rss_after_mb, 2))

        result["success"] = trimmed_count > 0
        result["processes_trimmed"] = trimmed_count
        result["rss_after_mb"] = rss_after_mb
        result["freed_mb"] = freed_mb
        return result
