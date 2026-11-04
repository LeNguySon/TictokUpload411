"""
Video Import Worker: Indexes, hashes, and registers video files from Explorer drag-and-drop
or file selection dialog in background QThreadPool without blocking Qt Main Thread.
Conforms to ECC Development Standards and guarantees zero GUI freeze.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from src.application.services.upload_service import UploadService

logger = logging.getLogger(__name__)


class VideoImportSignals(QObject):
    """Signals emitted during background video ingestion and hashing."""

    started = pyqtSignal()
    progress = pyqtSignal(int, int, str)  # current, total, filename
    completed = pyqtSignal(int)  # added_count
    failed = pyqtSignal(str)  # error_message
    finished = pyqtSignal()


class VideoImportWorker(QRunnable):
    """
    QRunnable worker executing SHA-256 calculation and video registration
    asynchronously, ensuring UI responsiveness even for large video files.
    """

    def __init__(
        self,
        file_paths: list[str],
        upload_service: UploadService,
        assigned_profile_id: int | None = None,
        schedule_time: str | None = None,
    ) -> None:
        super().__init__()
        self.file_paths = file_paths
        self.upload_service = upload_service
        self.assigned_profile_id = assigned_profile_id
        self.schedule_time = schedule_time

        self.signals = VideoImportSignals()
        self._cancelled: bool = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """Cooperatively cancels video import."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        """Processes file list, hashes files, and adds to queue."""
        self.signals.started.emit()
        added_count = 0
        total = len(self.file_paths)
        try:
            for idx, f in enumerate(self.file_paths, start=1):
                if self._cancelled:
                    logger.info("VideoImportWorker cancelled at %d/%d", idx, total)
                    break
                p = Path(f)
                self.signals.progress.emit(idx, total, p.name)
                try:
                    self.upload_service.enqueue_video(
                        file_path=p,
                        title=p.stem,
                        assigned_profile_id=self.assigned_profile_id,
                        schedule_time=self.schedule_time,
                    )
                    added_count += 1
                except Exception as file_err:
                    logger.error("Failed importing video %s: %s", f, file_err)

            self.signals.completed.emit(added_count)
        except Exception as e:
            logger.error("VideoImportWorker encountered fatal error: %s", e, exc_info=True)
            self.signals.failed.emit(str(e))
        finally:
            self.signals.finished.emit()
