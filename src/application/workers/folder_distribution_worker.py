"""
Folder Distribution Worker: Executes directory scanning, recursive indexing,
SHA-256 deduplication, spintax formatting, and atomic queue dispatch in background QThreadPool.
Conforms to ECC Development Standards and guarantees zero GUI freeze.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from src.application.services.upload_service import UploadService

logger = logging.getLogger(__name__)


class FolderDistributionSignals(QObject):
    """Signals emitted during folder distribution background tasks."""

    started = pyqtSignal()
    progress = pyqtSignal(int, int, str)  # current, total, filename
    completed = pyqtSignal(list)  # distributed items list
    failed = pyqtSignal(str)  # error message
    finished = pyqtSignal()


class FolderDistributionWorker(QRunnable):
    """
    QRunnable worker executing folder scanning, SHA-256 deduplication, and
    fair-share distribution across TikTok accounts on background thread.
    """

    def __init__(
        self,
        upload_service: UploadService,
        folder_path: str | Path | None = None,
        profile_ids: list[int] | None = None,
        project_batches: list[dict[str, Any]] | None = None,
        min_interval_hours: float = 12.0,
        random_order: bool = False,
        prioritize_newest: bool = True,
        deduplicate: bool = True,
        caption_template: str | None = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        allow_hd: bool = True,
        is_ai_generated: bool = False,
    ) -> None:
        super().__init__()
        self.upload_service = upload_service
        self.folder_path = folder_path
        self.profile_ids = profile_ids or []
        self.project_batches = project_batches
        self.min_interval_hours = min_interval_hours
        self.random_order = random_order
        self.prioritize_newest = prioritize_newest
        self.deduplicate = deduplicate
        self.caption_template = caption_template
        self.privacy = privacy
        self.allow_comment = allow_comment
        self.allow_duet = allow_duet
        self.allow_stitch = allow_stitch
        self.allow_hd = allow_hd
        self.is_ai_generated = is_ai_generated

        self.signals: FolderDistributionSignals = FolderDistributionSignals()
        self._cancelled: bool = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """Flags the worker for cooperative early termination."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        """Executes distribution in worker thread and reports progress/completion."""
        self.signals.started.emit()
        try:
            if self.project_batches is not None:
                items: list[dict[str, Any]] = self.upload_service.distribute_multi_project_batches(
                    project_batches=self.project_batches,
                    min_interval_hours=self.min_interval_hours,
                    random_order=self.random_order,
                    prioritize_newest=self.prioritize_newest,
                    deduplicate=self.deduplicate,
                    caption_template=self.caption_template,
                    privacy=self.privacy,
                    allow_comment=self.allow_comment,
                    allow_duet=self.allow_duet,
                    allow_stitch=self.allow_stitch,
                    allow_hd=self.allow_hd,
                    is_ai_generated=self.is_ai_generated,
                    progress_callback=lambda cur, tot, name: self.signals.progress.emit(cur, tot, name),
                    cancel_token=lambda: self._cancelled,
                )
            else:
                items = self.upload_service.distribute_folder_videos_to_queue(
                    folder_path=self.folder_path or "",
                    profile_ids=self.profile_ids,
                    min_interval_hours=self.min_interval_hours,
                    random_order=self.random_order,
                    prioritize_newest=self.prioritize_newest,
                    deduplicate=self.deduplicate,
                    caption_template=self.caption_template,
                    privacy=self.privacy,
                    allow_comment=self.allow_comment,
                    allow_duet=self.allow_duet,
                    allow_stitch=self.allow_stitch,
                    allow_hd=self.allow_hd,
                    is_ai_generated=self.is_ai_generated,
                    progress_callback=lambda cur, tot, name: self.signals.progress.emit(cur, tot, name),
                    cancel_token=lambda: self._cancelled,
                )
            self.signals.completed.emit(items)
        except Exception as e:
            logger.error("FolderDistributionWorker failed: %s", e, exc_info=True)
            self.signals.failed.emit(str(e))
        finally:
            self.signals.finished.emit()
