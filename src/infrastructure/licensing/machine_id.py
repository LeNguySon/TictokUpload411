"""Stable, privacy-preserving machine code: a short hash of the Windows MachineGuid and system volume serial."""

from __future__ import annotations

import ctypes
import hashlib
import os

_SALT = b"TAVM-machine-v1\x00"


def format_machine_code(machine_guid: str, volume_serial: str) -> str:
    digest = hashlib.sha256(_SALT + machine_guid.encode("utf-8") + b"\x00" + volume_serial.encode("utf-8"))
    hex16 = digest.hexdigest()[:16].upper()
    return "-".join(hex16[i : i + 4] for i in range(0, 16, 4))


def _machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            return str(winreg.QueryValueEx(key, "MachineGuid")[0])
    except Exception:
        return ""


def _system_volume_serial() -> str:
    try:
        drive = os.environ.get("SystemDrive", "C:") + os.sep
        serial = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(drive), None, 0, ctypes.byref(serial), None, None, None, 0
        )
        return f"{serial.value:08X}" if ok else ""
    except Exception:
        return ""


def machine_code() -> str:
    return format_machine_code(_machine_guid(), _system_volume_serial())
