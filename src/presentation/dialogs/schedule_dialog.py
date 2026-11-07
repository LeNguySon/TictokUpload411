"""
Schedule Video Dialog for planning staggered automated video uploads with jitter.
"""

import random
from datetime import datetime, timedelta

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    DateTimeEdit,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    SpinBox,
)

from src.domain.analytics.optimal_hours import peak_window
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    fit_dialog_to_content,
    style_card,
)


def round_to_nearest_5_minutes(minutes: int) -> int:
    """Rounds minute value to nearest multiple of 5, capped at 55."""
    rounded = round(minutes / 5) * 5
    if rounded >= 60:
        rounded = 55
    return rounded


def generate_staggered_schedule(
    start_time: datetime,
    count: int,
    interval_minutes: int = 30,
    random_jitter_minutes: int = 5,
    is_studio_schedule: bool = False,
) -> list[str]:
    """Generates a list of ISO-formatted datetime strings spaced by interval + jitter."""
    results = []
    current = start_time
    now = datetime.now()

    if is_studio_schedule:
        min_allowed = now + timedelta(minutes=15)
        if current < min_allowed:
            current = min_allowed

    for _ in range(count):
        jitter = random.randint(-abs(random_jitter_minutes), abs(random_jitter_minutes))
        scheduled_dt = current + timedelta(minutes=jitter)
        if is_studio_schedule:
            min_allowed = now + timedelta(minutes=15)
            max_allowed = now + timedelta(days=10)
            if scheduled_dt < min_allowed:
                scheduled_dt = min_allowed
            elif scheduled_dt > max_allowed:
                scheduled_dt = max_allowed
            # Round minutes to nearest 5
            rounded_minute = round_to_nearest_5_minutes(scheduled_dt.minute)
            scheduled_dt = scheduled_dt.replace(minute=rounded_minute, second=0)
            if scheduled_dt < min_allowed:
                scheduled_dt += timedelta(minutes=5)
        else:
            if scheduled_dt < start_time:
                scheduled_dt = start_time

        results.append(scheduled_dt.strftime("%Y-%m-%d %H:%M:%S"))
        current += timedelta(minutes=interval_minutes)
    return results


def _window_start_hour(window: str | None) -> int | None:
    """Start hour of a "HH:MM - HH:MM" window."""
    try:
        hour = int(str(window).split(":", 1)[0])
    except ValueError:
        return None
    return hour if 0 <= hour <= 23 else None


class ScheduleVideoDialog(QDialog):
    """
    Dialog allowing creators to set upload schedules with intervals and jitter to avoid anti-spam bans.
    Supports both Local Queue dispatch and TikTok Studio Native Cloud scheduling.
    """

    def __init__(
        self,
        video_count: int,
        optimal_hour: int | None = None,
        optimal_window: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.video_count = max(1, video_count)
        self.optimal_hour = optimal_hour
        self.optimal_window = optimal_window
        self.generated_schedules: list[str] = []
        self.is_studio_schedule: bool = False

        self.setWindowTitle("Lên Lịch Đăng Video Hàng Loạt")
        self.resize(500, 390)
        self._init_ui()
        fit_dialog_to_content(self)

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.CALENDAR,
            title="Lên Lịch Đăng Video Hàng Loạt",
            subtitle=f"Thiết lập lịch tự động cho {self.video_count} video đã chọn với khoảng cách và độ lệch jitter.",
            parent=self,
        )
        layout.addWidget(header)

        # Smart Posting Hour Recommendation Banner
        if self.optimal_hour is not None or self.optimal_window:
            window_text = self.optimal_window or peak_window(self.optimal_hour or 0)
            opt_frame = QFrame(self)
            style_card(opt_frame, kind="warning", object_name="optimalHourBanner")
            opt_lay = QHBoxLayout(opt_frame)
            opt_lay.setContentsMargins(12, 6, 12, 6)

            lbl_opt = QLabel(f"⚡ <b>Giờ vàng đề xuất cho kênh:</b> {window_text}")
            lbl_opt.setStyleSheet("font-size: 12px; color: #D97706;")
            opt_lay.addWidget(lbl_opt)
            opt_lay.addStretch(1)

            self.btn_use_optimal = PushButton(FluentIcon.SPEED_HIGH, "Đặt vào giờ vàng", self)
            self.btn_use_optimal.clicked.connect(self._set_to_next_optimal_hour)
            opt_lay.addWidget(self.btn_use_optimal)
            layout.addWidget(opt_frame)

        form = QFormLayout()
        form.setSpacing(10)

        # Start Date Time
        self.dt_start = DateTimeEdit(self)
        self.dt_start.setDateTime(QDateTime.currentDateTime().addSecs(1200))  # +20 minutes
        form.addRow("Thời gian bắt đầu:", self.dt_start)

        # Interval
        self.spin_interval = SpinBox(self)
        self.spin_interval.setRange(5, 720)
        self.spin_interval.setValue(30)
        form.addRow("Khoảng cách giữa các video (phút):", self.spin_interval)

        # Jitter
        self.spin_jitter = SpinBox(self)
        self.spin_jitter.setRange(0, 30)
        self.spin_jitter.setValue(5)
        form.addRow("Độ lệch ngẫu nhiên Jitter (phút):", self.spin_jitter)

        layout.addLayout(form)

        # TikTok Studio Native Cloud Option
        self.chk_studio_schedule = CheckBox("Lên lịch trực tiếp vào TikTok Studio (Cloud Schedule)", self)
        self.chk_studio_schedule.setToolTip(
            "Khi bật: Video sẽ được tải lên ngay và tick chọn 'Schedule' trong TikTok Studio.\n"
            "TikTok sẽ tự động xuất bản đúng giờ mà không cần mở máy tính (Cửa sổ 15 phút - 10 ngày)."
        )
        self.chk_studio_schedule.stateChanged.connect(self._on_studio_mode_changed)
        layout.addWidget(self.chk_studio_schedule)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_apply = PrimaryPushButton("Áp Dụng Lịch Đăng", self)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_layout)

    def _on_studio_mode_changed(self, state: int) -> None:
        if self.chk_studio_schedule.isChecked():
            # Studio requires at least 15m ahead
            current_dt = self.dt_start.dateTime()
            min_dt = QDateTime.currentDateTime().addSecs(1200)  # +20 min
            if current_dt < min_dt:
                self.dt_start.setDateTime(min_dt)

    def _set_to_next_optimal_hour(self) -> None:
        target_h = self.optimal_hour if self.optimal_hour is not None else _window_start_hour(self.optimal_window)
        if target_h is None:
            return
        now = datetime.now()
        candidate = now.replace(hour=target_h, minute=0, second=0, microsecond=0)
        if candidate <= now + timedelta(minutes=20):
            candidate += timedelta(days=1)
        self.dt_start.setDateTime(QDateTime(candidate))

    def _on_apply(self) -> None:
        qdt = self.dt_start.dateTime()
        py_dt = qdt.toPyDateTime()
        interval = self.spin_interval.value()
        jitter = self.spin_jitter.value()
        self.is_studio_schedule = self.chk_studio_schedule.isChecked()

        self.generated_schedules = generate_staggered_schedule(
            start_time=py_dt,
            count=self.video_count,
            interval_minutes=interval,
            random_jitter_minutes=jitter,
            is_studio_schedule=self.is_studio_schedule,
        )
        self.accept()
