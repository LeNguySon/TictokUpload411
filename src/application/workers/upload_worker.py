"""
Upload Worker executing video publishing on QThreadPool without blocking UI thread.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime

from sammonny import RemoteStatus

from src.application.services.upload_service import UploadService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker
from src.domain.licensing import entitlements
from src.domain.licensing.plans import Feature, upgrade_hint

logger = logging.getLogger(__name__)

# Max rate of progress/stage signals per video (chunk callbacks can fire hundreds of times/s).
PROGRESS_MIN_INTERVAL_S = 0.25


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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.video_id = video_id
        self.profile_id = profile_id
        self.upload_service = upload_service
        self.signal_bus = signal_bus or AppSignalBus.instance()
        self.schedule_time = schedule_time
        self._last_reported_milestone = -1
        self._clock = clock
        self._last_progress_emit = float("-inf")
        self._last_progress_pct = -1

    def _safe_emit(self, signal, *args) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def _emit_log(self, stage: str, message: str, level: str = "INFO") -> None:
        """Emits granular per-video log to central signal bus with timestamp."""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self.signal_bus.upload_log.emit(self.video_id, ts, stage, message, level)
        except RuntimeError:
            pass

    def _on_progress(self, uploaded_bytes: int, total_bytes: int, percentage: float) -> None:
        """Relays progress to the UI, rate-limited to PROGRESS_MIN_INTERVAL_S per video.

        The final 100% update is always delivered; the 25% milestone logs below are unaffected.
        """
        try:
            int_pct = int(percentage)
            now = self._clock()
            is_final = percentage >= 100.0
            due = now - self._last_progress_emit >= PROGRESS_MIN_INTERVAL_S
            if (due and int_pct != self._last_progress_pct) or (is_final and self._last_progress_pct < 100):
                self._last_progress_emit = now
                self._last_progress_pct = int_pct
                self.signals.progress.emit(uploaded_bytes, total_bytes, percentage)
                self.signal_bus.upload_progress.emit(self.video_id, uploaded_bytes, total_bytes, percentage)
                self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, f"Đang gửi {int_pct}%")

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
        except RuntimeError:
            pass

    def execute(self) -> None:
        if self.is_cancelled:
            return
        if not entitlements.has(Feature.UPLOAD):  # Gói 2+; also catches expiry while queued
            message = upgrade_hint(Feature.UPLOAD)
            self._emit_log("ERROR", message, "ERROR")
            self._safe_emit(self.signal_bus.upload_failed, self.video_id, message)
            return

        logger.info("Starting upload worker for video %s on profile %s", self.video_id, self.profile_id)
        self._emit_log("START", f"Bắt đầu upload video #{self.video_id} lên Kênh #{self.profile_id}")
        self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, "Khởi tạo...")
        self._safe_emit(self.signal_bus.upload_started, self.video_id, self.profile_id)

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
                self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, "Hoàn tất")
                self._safe_emit(self.signal_bus.upload_completed, self.video_id, result.publish_id or "")
            elif getattr(result, "status", None) == RemoteStatus.PENDING and not result.error:
                # Deferred to the app's scheduler (the method cannot schedule on TikTok): not a failure.
                self._emit_log("SCHEDULE", "Video được giữ lại, app sẽ tự đăng đúng giờ hẹn.", "INFO")
                self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, "Chờ tới giờ đăng")
            else:
                err_msg = result.error or "Upload unsuccessful"
                self._emit_log("ERROR", f"Upload thất bại: {err_msg}", "ERROR")
                self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, "Thất bại")
                self._safe_emit(self.signal_bus.upload_failed, self.video_id, err_msg)

        except Exception as e:
            logger.error("Upload worker error for video %s: %s", self.video_id, e)
            self._emit_log("ERROR", f"Ngoại lệ xử lý video #{self.video_id}: {str(e)}", "ERROR")
            self._safe_emit(self.signal_bus.upload_stage_changed, self.video_id, "Lỗi ngoại lệ")
            self._safe_emit(self.signal_bus.upload_failed, self.video_id, str(e))
            raise
