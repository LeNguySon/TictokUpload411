"""
Video Metadata Dialog for fine-tuning TikTok video title, tags, and privacy settings.
"""

from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
)


class VideoMetadataDialog(QDialog):
    """
    Dialog allowing creators to edit metadata (title, hashtags, privacy, stitch/duet flags) for a video.
    """

    def __init__(self, video_data: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.video_data = dict(video_data)

        self.setWindowTitle("Chỉnh Sửa Thông Tin Video")
        self.resize(500, 360)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # Title
        self.txt_title = LineEdit(self)
        self.txt_title.setText(self.video_data.get("file_name") or self.video_data.get("title", ""))
        form.addRow("Tiêu đề video:", self.txt_title)

        # Tags / Hashtags
        self.txt_tags = LineEdit(self)
        self.txt_tags.setPlaceholderText("#fyp #trending #viral...")
        form.addRow("Hashtags:", self.txt_tags)

        # Privacy
        self.combo_privacy = ComboBox(self)
        self.combo_privacy.addItem("Công khai (PUBLIC_TO_EVERYONE)", userData="PUBLIC_TO_EVERYONE")
        self.combo_privacy.addItem("Bạn bè (MUTUAL_FOLLOW_FRIENDS)", userData="MUTUAL_FOLLOW_FRIENDS")
        self.combo_privacy.addItem("Chỉ mình tôi (SELF_ONLY)", userData="SELF_ONLY")

        current_priv = self.video_data.get("privacy_level", "PUBLIC_TO_EVERYONE")
        for i in range(self.combo_privacy.count()):
            if self.combo_privacy.itemData(i) == current_priv:
                self.combo_privacy.setCurrentIndex(i)
                break
        form.addRow("Chế độ hiển thị:", self.combo_privacy)

        # Permissions
        self.chk_comments = QCheckBox("Cho phép bình luận (Allow Comments)", self)
        self.chk_comments.setChecked(True)
        form.addRow("Bình luận:", self.chk_comments)

        self.chk_duet = QCheckBox("Cho phép Duet", self)
        self.chk_duet.setChecked(True)
        form.addRow("Duet:", self.chk_duet)

        self.chk_stitch = QCheckBox("Cho phép Stitch", self)
        self.chk_stitch.setChecked(True)
        form.addRow("Stitch:", self.chk_stitch)

        layout.addLayout(form)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_save = PrimaryPushButton("Lưu Thông Tin", self)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        self.video_data["title"] = self.txt_title.text().strip()
        self.video_data["file_name"] = self.txt_title.text().strip()
        self.video_data["privacy_level"] = self.combo_privacy.currentData()
        self.video_data["allow_comment"] = self.chk_comments.isChecked()
        self.video_data["allow_duet"] = self.chk_duet.isChecked()
        self.video_data["allow_stitch"] = self.chk_stitch.isChecked()
        self.accept()
