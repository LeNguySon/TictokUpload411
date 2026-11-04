"""
Application Entrypoint: TikTok Manager (TAVM-2026-WIN)
Clean Architecture & ECC Industrial Standards.
"""

import logging
import sys
from pathlib import Path

import sammonny
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.connection import DEFAULT_DB_PATH
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.logging.redaction_logger import configure_app_logger
from src.presentation.views.main_window import TikTokManagerMainWindow

logger = logging.getLogger("TikTokManagerApp")


def main() -> None:
    # 1. Initialize Structured Logging with Redaction Filter (AgentShield Tier-1)
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    configure_app_logger(log_file=logs_dir / "app.log")

    logger.info("Initializing TikTok Manager TAVM-2026-WIN...")

    # 2. Database Migrations (WAL Mode, 24 Tables)
    applied = run_all_migrations(DEFAULT_DB_PATH)
    logger.info("Database migrations successfully executed. Total tables: %d", len(applied))

    # 3. Create Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("SSMATool Reup Tiktok")
    app.setOrganizationName("Goepro")

    # 4. Instantiate and display Fluent Windows 11 Main Window
    window = TikTokManagerMainWindow(db_path=DEFAULT_DB_PATH)
    window.show()

    # 5. Clean exit hook
    exit_code = app.exec()

    try:
        sammonny.MemoryManager.trim_working_set()
    except Exception:
        pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
