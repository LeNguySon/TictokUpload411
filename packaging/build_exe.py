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


def build(target: str) -> None:
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
