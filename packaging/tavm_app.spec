# PyInstaller spec — customer app (SonBetaPro). Build with: python packaging/build_exe.py app
# One-folder build: fast start-up; data/, logs/, profiles/ are created next to SonBetaPro.exe.
# The developer license issuer (tools/) is excluded on purpose and must never be shipped.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (provided by PyInstaller)

datas = [(str(ROOT / "icon.ico"), "."), (str(ROOT / "resources"), "resources")]
binaries = []
hiddenimports = collect_submodules("src") + collect_submodules("keyring.backends")
for pkg in ("qfluentwidgets", "sammonny", "curl_cffi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tools", "tests", "pytest", "tkinter", "PyQt5", "PySide2", "PySide6", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SonBetaPro",
    icon=str(ROOT / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SonBetaPro", upx=False)  # noqa: F821
