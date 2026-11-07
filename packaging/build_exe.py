"""Build the Windows executables.

    python packaging/build_exe.py app     -> dist/SonBetaPro/SonBetaPro.exe   (give this folder to customers)
    python packaging/build_exe.py admin   -> dist/TAVM-Admin.exe              (developer only, never ship)
    python packaging/build_exe.py all

Before building the app, every signing key you issue with must be listed in
src/infrastructure/licensing/trusted_keys.py (the admin tool warns when it is not).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = {"app": "tavm_app.spec", "admin": "tavm_admin.spec"}


def pinned_versions() -> dict[str, str]:
    """Exact pins (``name==x.y.z``) from pyproject.toml's dependencies."""
    import re
    import tomllib

    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    return {m.group(1): m.group(2) for d in deps if (m := re.match(r"^\s*([A-Za-z0-9_.-]+)==([^;\s]+)", d))}


def environment_problems(installed: dict[str, str] | None = None) -> list[str]:
    """Why this Python must not build the app (empty list = OK).

    The shipped exe was once built with the system Python (sammonny 1.5.0, PyQt6 6.12): build only from the
    project's .venv with the pinned SDK and a PyQt6 whose stubs/runtime match the tests (< 6.12)."""
    from importlib import metadata

    def version(dist: str) -> str | None:
        if installed is not None:
            return installed.get(dist)
        try:
            return metadata.version(dist)
        except metadata.PackageNotFoundError:
            return None

    problems: list[str] = []
    for dist, wanted in pinned_versions().items():
        got = version(dist)
        if got != wanted:
            problems.append(f"{dist} {got or 'not installed'} != pinned {wanted}")
    pyqt = version("PyQt6")
    if pyqt is None or tuple(int(x) for x in pyqt.split(".")[:2]) >= (6, 12):
        problems.append(f"PyQt6 {pyqt or 'not installed'} must be < 6.12")
    return problems


def build(target: str) -> None:
    problems = environment_problems()
    if problems:
        bullet = "\n  - "
        raise SystemExit(
            f"Refusing to build from this Python ({sys.executable}):{bullet}{bullet.join(problems)}\n"
            "Run with the project's .venv: .venv\\Scripts\\python packaging/build_exe.py app"
        )
    spec = ROOT / "packaging" / SPECS[target]
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / target),
        str(spec),
    ]
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main(argv: list[str]) -> int:
    targets = argv[1:] or ["all"]
    if targets == ["all"]:
        targets = list(SPECS)
    unknown = [t for t in targets if t not in SPECS]
    if unknown:
        print(f"Unknown target(s): {unknown}; use app, admin or all")
        return 2
    for target in targets:
        build(target)
    print("Done. Output in", ROOT / "dist")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
