"""Local license storage: the key and the latest wall-clock time seen, DPAPI-encrypted for the current user."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.infrastructure.credentials.dpapi import SecretProtectionError, protect_bytes, unprotect_bytes

logger = logging.getLogger(__name__)

LICENSE_FILE_ENV = "TAVM_LICENSE_FILE"
_PURPOSE = "tavm-license-v1"


def default_license_path() -> Path:
    override = os.environ.get(LICENSE_FILE_ENV)
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "TAVM" / "license.dat"


class LicenseStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_license_path()

    def _read(self) -> dict[str, Any]:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.warning("License file unreadable: %s", exc)
            return {}
        try:
            data = json.loads(unprotect_bytes(raw, _PURPOSE).decode("utf-8"))
        except (SecretProtectionError, ValueError, UnicodeError):
            logger.warning("License file is corrupted or belongs to another Windows user; ignoring it")
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(protect_bytes(json.dumps(data).encode("utf-8"), _PURPOSE))
        os.replace(tmp, self.path)

    def load_key(self) -> str | None:
        key = self._read().get("key")
        return key if isinstance(key, str) and key else None

    def save_key(self, key: str) -> None:
        data = self._read()
        data["key"] = key
        self._write(data)

    def last_seen(self) -> float | None:
        value = self._read().get("last_seen")
        return float(value) if isinstance(value, int | float) else None

    def touch(self, now: float) -> None:
        """Records the latest time seen; never moves backwards (clock-rollback detection)."""
        data = self._read()
        previous = data.get("last_seen")
        if isinstance(previous, int | float) and previous >= now:
            return
        data["last_seen"] = float(now)
        self._write(data)
