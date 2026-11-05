# PyInstaller spec — developer-only license issuer GUI (TAVM-Admin.exe). NEVER give this file to customers.
# Build with: python packaging/build_exe.py admin
# One-file build. Signing keys stay in %LOCALAPPDATA%\TAVM-Issuer (DPAPI), never inside the exe.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent  # noqa: F821 (provided by PyInstaller)

datas = [(str(ROOT / "icon.ico"), "."), (str(ROOT / "resources"), "resources")]
d, binaries, hiddenimports = collect_all("qfluentwidgets")
datas += d

a = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "license_issuer" / "admin_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tests", "pytest", "tkinter", "PyQt5", "PySide2", "PySide6"],  # src package __init__ chains import the SDK: keep it
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TAVM-Admin",
    icon=str(ROOT / "icon.ico"),
    console=False,
    upx=False,
)
