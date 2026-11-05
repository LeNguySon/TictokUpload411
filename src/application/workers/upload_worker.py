"""
Upload Worker executing video publishing on QThreadPool without blocking UI thread.
"""

import logging
from datetime import datetime

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
        self._last_reported_milestone = -1

    def _emit_log(self, stage: str, message: str, level: str = "INFO") -> None:
        """Emits granular per-video log to central signal bus with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.signal_bus.upload_log.emit(self.video_id, ts, stage, message, level)

    def _on_progress(self, uploaded_bytes: int, total_bytes: int, percentage: float) -> None:
        """Relays progress updates to both local worker signals and the global event bus."""
        self.signals.progress.emit(uploaded_bytes, total_bytes, percentage)
        self.signal_bus.upload_progress.emit(self.video_id, uploaded_bytes, total_bytes, percentage)

        int_pct = int(percentage)
        self.signal_bus.upload_stage_changed.emit(self.video_id, f"Đang gửi {int_pct}%")

        # Emit log on 25% milestones (25, 50, 75, 100) or at start of chunking
        milestone = (int_pct // 25) * 25
        if milestone > self._last_reported_milestone and milestone > 0:
            self._last_reported_milestone = milestone
            up_mb = uploaded_bytes / (1024 * 1024) if uploaded_bytes else 0.0
            tot_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
            self._emit_log(
                "CHUNK",
                f"Tiến độ upload: {up_mb:.1f} MB / {tot_mb:.1f} MB ({percentage:.1f}%)",
                "INFO",
            )

    def execute(self) -> None:
        if self.is_cancelled:
            return

        logger.info("Starting upload worker for video %s on profile %s", self.video_id, self.profile_id)
        self._emit_log("START", f"Bắt đầu upload video #{self.video_id} lên Kênh #{self.profile_id}")
        self.signal_bus.upload_stage_changed.emit(self.video_id, "Khởi tạo...")
        self.signal_bus.upload_started.emit(self.video_id, self.profile_id)

        def cancel_token() -> bool:
            return self.is_cancelled

        try:
            # Use inspect/getattr safe call if upload_service accepts log_callback
            result = self.upload_service.execute_upload(
                video_id=self.video_id,
                profile_id=self.profile_id,
                schedule_time=self.schedule_time,
                progress_callback=self._on_progress,
                cancel_token=cancel_token,
                log_callback=self._emit_log,
            )

            if result.success:
                pub_id = result.publish_id or "SUCCESS"
                self._emit_log("SUCCESS", f"Xuất bản TikTok thành công! ID: {pub_id}", "SUCCESS")
                self.signal_bus.upload_stage_changed.emit(self.video_id, "Hoàn tất")
                self.signal_bus.upload_completed.emit(self.video_id, result.publish_id or "")
            else:
                err_msg = result.error or "Upload unsuccessful"
                self._emit_log("ERROR", f"Upload thất bại: {err_msg}", "ERROR")
                self.signal_bus.upload_stage_changed.emit(self.video_id, "Thất bại")
                self.signal_bus.upload_failed.emit(self.video_id, err_msg)

        except Exception as e:
            logger.error("Upload worker error for video %s: %s", self.video_id, e)
            self._emit_log("ERROR", f"Ngoại lệ xử lý video #{self.video_id}: {str(e)}", "ERROR")
            self.signal_bus.upload_stage_changed.emit(self.video_id, "Lỗi ngoại lệ")
            self.signal_bus.upload_failed.emit(self.video_id, str(e))
            raise
