"""
Application branding and icon resolution module for SonBetaPro.
Loads the high-DPI multi-resolution Windows icon from icon.ico.
"""

from pathlib import Path

from PyQt6.QtGui import QIcon


def get_app_icon() -> QIcon:
    """
    Returns the application QIcon loaded from icon.ico.
    Searches standard project and resource directories for maximum portability.
    """
    candidates = [
        Path("D:/TictokUpload411/icon.ico"),
        Path(__file__).resolve().parent.parent.parent / "icon.ico",
        Path(__file__).resolve().parent.parent.parent / "resources" / "icons" / "app_icon.ico",
        Path("resources/icons/app_icon.ico"),
        Path("icon.ico"),
    ]
    for p in candidates:
        if p.is_file():
            icon = QIcon(str(p))
            if not icon.isNull():
                return icon
    return QIcon()

