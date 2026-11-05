"""
Application Entrypoint: TikTok Manager (TAVM-2026-WIN)
Clean Architecture & ECC Industrial Standards.
"""

import logging
import os
import sys
import traceback
from pathlib import Path

import sammonny
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog
from src.application.services.license_service import LicenseService
from src.infrastructure.database.connection import DEFAULT_DB_PATH
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.logging.redaction_logger import configure_app_logger
from src.presentation.app_icon import get_app_icon
from src.presentation.dialogs.license_activation_dialog import LicenseActivationDialog
from src.presentation.views.main_window import TikTokManagerMainWindow
from src.presentation.widgets.fluent_compat import apply_fluent_compat_patches

logger = logging.getLogger("tavm")


def global_exception_hook(exctype, value, tb):
    """Crash-Proof Guardian: Catches unhandled exceptions, logs them with redaction, and prevents silent app crash."""
    tb_lines = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical("Unhandled Exception Caught:\n%s", tb_lines)


sys.excepthook = global_exception_hook


def ensure_portable_workdir() -> None:
    """Packaged exe: data/, logs/ and profiles/ live next to the exe, whatever folder it is started from."""
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)


def main() -> None:
    ensure_portable_workdir()
    # 0. Windows Console UTF-8 Encoding & Taskbar AppUserModelID Hook
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SonBetaPro.App.2026")
        except Exception:
            pass

    # 1. Initialize Structured Logging with Redaction Filter (AgentShield Tier-1)
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    configure_app_logger(log_file=logs_dir / "app.log")

    logger.info("Initializing SonBetaPro TAVM-2026-WIN...")

    # 2. Database Migrations (WAL Mode, 24 Tables)
    applied = run_all_migrations(DEFAULT_DB_PATH)
    logger.info("Database migrations successfully executed. Total tables: %d", len(applied))

    # 3. Create Qt Application with Windows 11 High-DPI Crisp Rendering
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    apply_fluent_compat_patches()  # SpinBox value invisible on Qt 6.12 + Fluent 1.11 otherwise
    app.setApplicationName("SonBetaPro")
    app.setApplicationDisplayName("SonBetaPro")
    app.setOrganizationName("Goepro")

    # Set Application Icon (High-DPI multi-resolution from icon.ico)
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Set native Windows 11 Fluent font
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(9)
    app.setFont(font)

    # 4. License gate: offline Ed25519 key bound to this machine. Without a valid one the app stays locked.
    license_service = LicenseService()
    state = license_service.validate()
    if not state.ok and LicenseActivationDialog(license_service, state).exec() != QDialog.DialogCode.Accepted:
        logger.info("No valid license (%s); exiting.", license_service.state.status.value)
        sys.exit(0)

    # 5. Instantiate and display Fluent Windows 11 Main Window
    window = TikTokManagerMainWindow(db_path=DEFAULT_DB_PATH, license_service=license_service)
    window.show()

    # 6. Clean exit hook
    exit_code = app.exec()

    try:
        sammonny.MemoryManager.trim_process_tree_memory(os.getpid())
    except Exception:
        pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
