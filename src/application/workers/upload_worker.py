"""
Upload Worker executing video publishing on QThreadPool without blocking UI thread.
"""

import logging

from src.application.services.upload_service import UploadService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class UploadWorker(BaseWorker):
    """
    Background worker orchestrating video upload via SamMonny adapter.
    """

    def __init__(
        self,
        video_id: int,
        profile_id: int,
        upload_service: UploadService,
        signal_bus: AppSignalBus | None = None,
        schedule_time: str | None = None,
    ) -> None:
        super().__init__()
        self.video_id = video_id
        self.profile_id = profile_id
        self.upload_service = upload_service
        self.signal_bus = signal_bus or AppSignalBus.instance()
        self.schedule_time = schedule_time

    def _on_progress(self, uploaded_bytes: int, total_bytes: int, percentage: float) -> None:
        """Relays progress updates to both local worker signals and the global event bus."""
        self.signals.progress.emit(uploaded_bytes, total_bytes, percentage)
        self.signal_bus.upload_progress.emit(self.video_id, uploaded_bytes, total_bytes, percentage)

    def execute(self) -> None:
        if self.is_cancelled:
            return

        logger.info("Starting upload worker for video %s on profile %s", self.video_id, self.profile_id)
        self.signal_bus.upload_started.emit(self.video_id, self.profile_id)

        def cancel_token() -> bool:
            return self.is_cancelled

        try:
            result = self.upload_service.execute_upload(
                video_id=self.video_id,
                profile_id=self.profile_id,
                schedule_time=self.schedule_time,
                progress_callback=self._on_progress,
                cancel_token=cancel_token,
            )

            if result.success:
                self.signal_bus.upload_completed.emit(self.video_id, result.publish_id or "")
            else:
                self.signal_bus.upload_failed.emit(self.video_id, result.error or "Upload unsuccessful")

        except Exception as e:
            logger.error("Upload worker error for video %s: %s", self.video_id, e)
            self.signal_bus.upload_failed.emit(self.video_id, str(e))
            raise
