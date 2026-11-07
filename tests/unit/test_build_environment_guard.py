"""
The shipped SonBetaPro.exe was built with the system Python, whose environment had sammonny 1.5.0 (editable)
instead of the pinned 1.8.4 and pulled in numpy/scipy/pandas. The build script now refuses such environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("build_exe", Path("packaging/build_exe.py"))
assert _SPEC and _SPEC.loader
build_exe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_exe)


def test_pinned_versions_are_read_from_pyproject() -> None:
    pins = build_exe.pinned_versions()
    assert pins["sammonny"] == "1.8.5"


def test_current_venv_passes_the_guard() -> None:
    assert build_exe.environment_problems() == []


def test_wrong_sdk_or_pyqt_is_refused() -> None:
    problems = build_exe.environment_problems(installed={"sammonny": "1.5.0", "PyQt6": "6.12.0"})
    assert any("sammonny" in p and "1.5.0" in p for p in problems)
    assert any("PyQt6" in p and "6.12.0" in p for p in problems)
