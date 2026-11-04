"""
Schedule Video Dialog for planning staggered automated video uploads with jitter.
"""

import random
from datetime import datetime, timedelta

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    SpinBox,
)


def generate_staggered_schedule(
    start_time: datetime,
    count: int,
    interval_minutes: int = 30,
    random_jitter_minutes: int = 5,
) -> list[str]:
    """Generates a list of ISO-formatted datetime strings spaced by interval + jitter."""
    results = []
    current = start_time
    for _ in range(count):
        jitter = random.randint(-abs(random_jitter_minutes), abs(random_jitter_minutes))
        scheduled_dt = current + timedelta(minutes=jitter)
        if scheduled_dt < start_time:
            scheduled_dt = start_time
        results.append(scheduled_dt.strftime("%Y-%m-%d %H:%M:%S"))
        current += timedelta(minutes=interval_minutes)
    return results


class ScheduleVideoDialog(QDialog):
    """
    Dialog allowing creators to set upload schedules with intervals and jitter to avoid anti-spam bans.
    """

    def __init__(self, video_count: int, parent=None) -> None:
        super().__init__(parent)
        self.video_count = max(1, video_count)
        self.generated_schedules: list[str] = []

        self.setWindowTitle("Lên Lịch Đăng Video Hàng Loạt")
        self.resize(460, 320)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel(f"Lên lịch tự động cho <b>{self.video_count}</b> video đã chọn:"))

        form = QFormLayout()
        form.setSpacing(10)

        # Start Date Time
        self.dt_start = QDateTimeEdit(self)
        self.dt_start.setDateTime(QDateTime.currentDateTime().addSecs(300))  # +5 minutes
        self.dt_start.setCalendarPopup(True)
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

    def _on_apply(self) -> None:
        qdt = self.dt_start.dateTime()
        py_dt = qdt.toPyDateTime()
        interval = self.spin_interval.value()
        jitter = self.spin_jitter.value()

        self.generated_schedules = generate_staggered_schedule(
            start_time=py_dt,
            count=self.video_count,
            interval_minutes=interval,
            random_jitter_minutes=jitter,
        )
        self.accept()
