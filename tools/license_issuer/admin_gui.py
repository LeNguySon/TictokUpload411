"""TAVM Admin — graphical license issuer (developer only, never shipped with the customer app).

Uses the same signing-key store and ledger as the CLI (``issuer.py``).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PasswordLineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    TableWidget,
)
from src.domain.licensing.plans import PLAN_DISPLAY_NAMES, Plan
from src.infrastructure.licensing.trusted_keys import TRUSTED_PUBLIC_KEYS
from src.presentation.dialogs.dialog_helpers import create_dialog_header
from src.presentation.widgets.fluent_compat import apply_fluent_compat_patches

from tools.license_issuer import issuer

DAY = 86400


class _PasswordDialog(QDialog):
    def __init__(self, confirm: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mật khẩu sao lưu")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(QLabel("Mật khẩu bảo vệ file sao lưu khóa ký (tối thiểu 8 ký tự):", self))
        self.txt_pw = PasswordLineEdit(self)
        layout.addWidget(self.txt_pw)
        self.txt_pw2: PasswordLineEdit | None = None
        if confirm:
            self.txt_pw2 = PasswordLineEdit(self)
            self.txt_pw2.setPlaceholderText("Nhập lại mật khẩu")
            layout.addWidget(self.txt_pw2)
        self.lbl_error = QLabel("", self)
        self.lbl_error.setStyleSheet("color: #C42B1C;")
        layout.addWidget(self.lbl_error)
        row = QHBoxLayout()
        row.addStretch()
        cancel = PushButton("Hủy", self)
        cancel.clicked.connect(self.reject)
        ok = PrimaryPushButton("Đồng ý", self)
        ok.clicked.connect(self._on_ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)

    def _on_ok(self) -> None:
        if len(self.txt_pw.text()) < 8:
            self.lbl_error.setText("Mật khẩu phải có ít nhất 8 ký tự.")
            return
        if self.txt_pw2 is not None and self.txt_pw2.text() != self.txt_pw.text():
            self.lbl_error.setText("Hai mật khẩu không khớp.")
            return
        self.accept()

    def password(self) -> bytes:
        return str(self.txt_pw.text()).encode("utf-8")


class IssuerAdminWindow(QWidget):
    LEDGER_COLUMNS = ["issued_at", "sub", "plan", "mid", "expires", "kid", "lid", "note"]
    LEDGER_HEADERS = ["Ngày cấp", "Khách hàng", "Gói", "Mã máy", "Hết hạn", "Khóa ký", "Mã license", "Ghi chú"]

    def __init__(
        self, home: Path | None = None, trusted: Mapping[str, str] | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        apply_fluent_compat_patches()
        self.home = Path(home) if home else issuer.default_home()
        self.trusted = TRUSTED_PUBLIC_KEYS if trusted is None else trusted
        self.setWindowTitle("TAVM Admin — Cấp key bản quyền")
        self.resize(980, 720)
        self._init_ui()
        self._reload_kids()
        self._reload_ledger()
        self._update_expiry_preview()

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(
            create_dialog_header(
                icon=FluentIcon.CERTIFICATE,
                title="TAVM Admin — Cấp key bản quyền",
                subtitle="Nhận mã máy từ khách, chọn gói và thời hạn, rồi gửi lại key đã ký.",
                parent=self,
            )
        )

        # Signing key
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("<b>Khóa ký:</b>", self))
        self.cmb_kid = ComboBox(self)
        self.cmb_kid.setMinimumWidth(160)
        self.cmb_kid.currentIndexChanged.connect(self._on_kid_changed)
        key_row.addWidget(self.cmb_kid)
        self.txt_public_key = LineEdit(self)
        self.txt_public_key.setReadOnly(True)
        self.txt_public_key.setPlaceholderText("Public key")
        key_row.addWidget(self.txt_public_key, 1)
        self.btn_keygen = PushButton(FluentIcon.ADD, "Tạo khóa mới", self)
        self.btn_keygen.clicked.connect(self._on_keygen)
        key_row.addWidget(self.btn_keygen)
        self.btn_backup = PushButton(FluentIcon.SAVE, "Sao lưu", self)
        self.btn_backup.clicked.connect(self._on_backup)
        key_row.addWidget(self.btn_backup)
        self.btn_restore = PushButton(FluentIcon.SYNC, "Khôi phục", self)
        self.btn_restore.clicked.connect(self._on_restore)
        key_row.addWidget(self.btn_restore)
        layout.addLayout(key_row)

        self.lbl_trust = QLabel(self)
        self.lbl_trust.setWordWrap(True)
        self.lbl_trust.setStyleSheet("color: #C42B1C; font-weight: 600;")
        layout.addWidget(self.lbl_trust)

        # Issue form
        form = QFormLayout()
        form.setSpacing(10)
        self.txt_sub = LineEdit(self)
        self.txt_sub.setPlaceholderText("Tên hiển thị trên app: Xin chào …")
        form.addRow("Khách hàng:", self.txt_sub)
        self.cmb_plan = ComboBox(self)
        for plan in Plan:
            self.cmb_plan.addItem(PLAN_DISPLAY_NAMES[plan], userData=plan.value)
        self.cmb_plan.setCurrentIndex(self.cmb_plan.findData(Plan.PRO.value))
        form.addRow("Gói:", self.cmb_plan)
        self.txt_mid = LineEdit(self)
        self.txt_mid.setPlaceholderText("XXXX-XXXX-XXXX-XXXX (khách sao chép trong hộp thoại Kích hoạt bản quyền)")
        form.addRow("Mã máy:", self.txt_mid)
        days_row = QHBoxLayout()
        self.spin_days = SpinBox(self)
        self.spin_days.setRange(1, 3650)
        self.spin_days.setValue(30)
        self.spin_days.valueChanged.connect(self._update_expiry_preview)
        days_row.addWidget(self.spin_days)
        for label, days in (("1 tháng", 30), ("3 tháng", 90), ("6 tháng", 180), ("1 năm", 365)):
            btn = PushButton(label, self)
            btn.clicked.connect(lambda _=False, d=days: self.spin_days.setValue(d))
            days_row.addWidget(btn)
        self.lbl_expiry = QLabel(self)
        days_row.addWidget(self.lbl_expiry)
        days_row.addStretch()
        form.addRow("Số ngày:", days_row)
        self.txt_note = LineEdit(self)
        self.txt_note.setPlaceholderText("Ghi chú nội bộ (mã đơn hàng, liên hệ…)")
        form.addRow("Ghi chú:", self.txt_note)
        layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.btn_issue = PrimaryPushButton(FluentIcon.CERTIFICATE, "Cấp key", self)
        self.btn_issue.clicked.connect(self._on_issue)
        action_row.addWidget(self.btn_issue)
        layout.addLayout(action_row)

        out_row = QHBoxLayout()
        self.txt_output = PlainTextEdit(self)
        self.txt_output.setReadOnly(True)
        self.txt_output.setPlaceholderText("Key đã cấp sẽ hiện ở đây — gửi nguyên văn cho khách.")
        self.txt_output.setFixedHeight(90)
        out_row.addWidget(self.txt_output, 1)
        self.btn_copy = PushButton(FluentIcon.COPY, "Sao chép key", self)
        self.btn_copy.clicked.connect(self._on_copy)
        out_row.addWidget(self.btn_copy, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(out_row)

        layout.addWidget(QLabel("<b>Sổ key đã cấp</b> (không lưu nội dung key):", self))
        self.tbl_ledger = TableWidget(self)
        self.tbl_ledger.setColumnCount(len(self.LEDGER_COLUMNS))
        self.tbl_ledger.setHorizontalHeaderLabels(self.LEDGER_HEADERS)
        self.tbl_ledger.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_ledger.verticalHeader().setVisible(False)
        # Fixed widths: ResizeToContents queries the Fluent delegate's sizeHint during teardown -> access violation.
        self.tbl_ledger.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((150, 160, 150, 150, 150, 80, 260)):
            self.tbl_ledger.setColumnWidth(col, width)
        self.tbl_ledger.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tbl_ledger, 1)

    # ------------------------------------------------------------- state
    def current_kid(self) -> str:
        return self.cmb_kid.currentData() or ""

    def _reload_kids(self, select: str | None = None) -> None:
        self.cmb_kid.blockSignals(True)
        self.cmb_kid.clear()
        for kid in issuer.list_kids(self.home):
            label = kid if kid in self.trusted else f"{kid} (app chưa tin)"
            self.cmb_kid.addItem(label, userData=kid)
        self.cmb_kid.blockSignals(False)
        trusted_kids = [i for i in range(self.cmb_kid.count()) if self.cmb_kid.itemData(i) in self.trusted]
        if select is not None and self.cmb_kid.findData(select) >= 0:
            self.cmb_kid.setCurrentIndex(self.cmb_kid.findData(select))
        elif trusted_kids:
            self.cmb_kid.setCurrentIndex(trusted_kids[-1])
        self._on_kid_changed()

    def _on_kid_changed(self, *_args: object) -> None:
        kid = self.current_kid()
        pub = ""
        if kid:
            try:
                pub = issuer.public_key(self.home, kid)
            except Exception as exc:
                self.lbl_trust.setText(f"Không đọc được khóa ký {kid}: {exc}")
                self.lbl_trust.show()
                self.txt_public_key.clear()
                self.btn_issue.setEnabled(False)
                return
        self.txt_public_key.setText(pub)
        if not kid:
            warning = "Chưa có khóa ký. Bấm 'Tạo khóa mới' hoặc 'Khôi phục' từ file sao lưu."
        elif self.trusted.get(kid) != pub:
            warning = (
                f"Bản app hiện tại KHÔNG tin khóa '{kid}': key cấp ra sẽ bị từ chối. Thêm "
                f"'{kid}': '{pub}' vào src/infrastructure/licensing/trusted_keys.py rồi build lại app."
            )
        else:
            warning = ""
        self.lbl_trust.setText(warning)
        self.lbl_trust.setVisible(bool(warning))
        self.btn_issue.setEnabled(not warning)
        self.btn_backup.setEnabled(bool(kid))

    def _reload_ledger(self) -> None:
        rows = issuer.read_ledger(self.home)
        self.tbl_ledger.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, col in enumerate(self.LEDGER_COLUMNS):
                value = row.get(col, "")
                if col == "plan":
                    try:
                        value = PLAN_DISPLAY_NAMES[Plan(value)]
                    except ValueError:
                        pass
                self.tbl_ledger.setItem(r, c, QTableWidgetItem(value))

    def _update_expiry_preview(self, *_args: object) -> None:
        exp = time.time() + self.spin_days.value() * DAY
        self.lbl_expiry.setText(f"→ hết hạn {time.strftime('%d-%m-%Y', time.localtime(exp))}")

    def _info(self, kind: str, title: str, content: str) -> None:
        getattr(InfoBar, kind)(title=title, content=content, position=InfoBarPosition.TOP, duration=5000, parent=self)

    # ----------------------------------------------------------- actions
    def _on_issue(self) -> None:
        try:
            key = issuer.issue(
                self.home,
                kid=self.current_kid(),
                sub=self.txt_sub.text(),
                plan=self.cmb_plan.currentData(),
                mid=self.txt_mid.text(),
                days=self.spin_days.value(),
                note=self.txt_note.text().strip(),
            )
        except Exception as exc:
            self._info("error", "Không cấp được key", str(exc))
            return
        self.txt_output.setPlainText(key)
        self._reload_ledger()
        self._info("success", "Đã cấp key", f"{self.cmb_plan.currentText()} cho {self.txt_sub.text().strip()}")

    def _on_copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None and self.txt_output.toPlainText():
            clipboard.setText(self.txt_output.toPlainText())
            self._info("success", "Đã sao chép", "Key đã nằm trong clipboard.")

    def _on_keygen(self) -> None:
        confirm = MessageBox(
            "Tạo khóa ký mới?",
            "Thường KHÔNG cần: chỉ tạo khi muốn đổi khóa (vd lộ khóa cũ).\n\n"
            "Key ký bằng khóa mới chỉ dùng được sau khi bạn thêm khóa vào trusted_keys.py, build lại app và gửi "
            "bản app mới cho khách. Khách đang dùng key cũ vẫn chạy bình thường.",
            self,
        )
        confirm.yesButton.setText("Tạo khóa mới")
        confirm.cancelButton.setText("Hủy")
        if not confirm.exec():
            return
        kid, pub = issuer.keygen(self.home)
        self._reload_kids(select=kid)
        MessageBox(
            "Đã tạo khóa ký mới",
            f"Khóa '{kid}' đã được tạo và mã hóa cho user Windows này.\n\n"
            f"Để app chấp nhận key ký bằng khóa này, thêm vào trusted_keys.py rồi build lại app:\n"
            f"'{kid}': '{pub}'\n\nHãy bấm 'Sao lưu' ngay.",
            self,
        ).exec()

    def _do_backup(self, out: Path, password: bytes) -> None:
        issuer.backup(self.home, self.current_kid(), Path(out), password)

    def _do_restore(self, kid: str, src: Path, password: bytes) -> None:
        issuer.restore(self.home, kid, Path(src), password)
        self._reload_kids(select=kid)

    def _on_backup(self) -> None:
        kid = self.current_kid()
        path, _ = QFileDialog.getSaveFileName(self, "Sao lưu khóa ký", f"{kid}.pem", "PEM (*.pem)")
        if not path:
            return
        dlg = _PasswordDialog(confirm=True, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._do_backup(Path(path), dlg.password())
        except Exception as exc:
            self._info("error", "Sao lưu thất bại", str(exc))
            return
        self._info("success", "Đã sao lưu", f"{kid} → {path}. Cất file và mật khẩu ở nơi an toàn, tách riêng nhau.")

    def _on_restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Khôi phục khóa ký", "", "PEM (*.pem)")
        if not path:
            return
        kid = Path(path).stem
        dlg = _PasswordDialog(confirm=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._do_restore(kid, Path(path), dlg.password())
        except Exception as exc:
            self._info("error", "Khôi phục thất bại", f"{exc} (sai mật khẩu hoặc khóa '{kid}' đã tồn tại?)")
            return
        self._info("success", "Đã khôi phục", f"Khóa ký {kid}")
