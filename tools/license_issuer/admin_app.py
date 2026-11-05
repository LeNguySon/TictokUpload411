"""Entry point of the TAVM Admin (license issuer) desktop tool — developer only."""

from __future__ import annotations

import sys


def main() -> int:
    from PyQt6.QtWidgets import QApplication
    from src.presentation.app_icon import get_app_icon
    from src.presentation.widgets.fluent_compat import apply_fluent_compat_patches

    from tools.license_issuer.admin_gui import IssuerAdminWindow

    app = QApplication(sys.argv)
    apply_fluent_compat_patches()
    app.setApplicationName("TAVM Admin")
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(9)
    app.setFont(font)

    window = IssuerAdminWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
