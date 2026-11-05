# Instinct 042: Dialog Visual Audit — Fluent Compat, Mnemonics, Scoped Styles

Bổ sung cho instinct 030 (chuẩn dialog). Kiểm toán bằng ảnh chụp **nền tảng Windows thật** của cả 19 dialog
(`scratch/perf/shoot_dialogs.py`, dữ liệu giả, `WA_DontShowOnScreen`). Test tự động áp lên MỌI dialog:
`tests/unit/test_dialog_design_standards.py`.

## 1. SpinBox / DateTimeEdit Fluent không hiện giá trị (Qt 6.12 + PyQt6-Fluent-Widgets 1.11.3)
- QLineEdit bên trong bị Qt đặt rộng 1px. `src/presentation/widgets/fluent_compat.py::apply_fluent_compat_patches()`
  đặt lại vùng chữ theo padding QSS của Fluent (trái 10px; phải 80px inline / 26px compact). Được gọi ở `main.py`,
  `TikTokManagerMainWindow.__init__` và `create_dialog_header` (idempotent, tự tắt nếu Qt/thư viện không còn lỗi).
- `SpinBox` inline cần ≥ ~110px. Ô hẹp (70px) dùng `CompactSpinBox`.
- Không dùng `setCalendarPopup(True)` trên `DateTimeEdit` Fluent (hiện mũi tên native thô).

## 2. Ký tự "&" trong text của nút / checkbox / QGroupBox / tab
- Qt coi "&" là phím tắt và ẩn nó ("Sức Khỏe  Thống Kê"). Phải viết **"&&"**. QLabel và window title thì không.

## 3. Không bao giờ `setStyleSheet("prop: ...")` trần trên container
- Thuộc tính không có selector lan xuống mọi con: mọi QLabel trong thẻ bị viền/nền. Dùng `style_card(frame, kind, object_name)`
  (selector `QFrame#name`).
- Không `setStyleSheet` trên nút Fluent (kể cả `""`): ghi đè stylesheet Fluent ⇒ nút thành Qt thô, mất icon.

## 4. Theme & màu
- App là giao diện sáng Fluent; không ép nền tối trong dialog (AccountHealthDialog cũ: tiêu đề tối trên nền tối).
- Màu trạng thái dùng `status_color(kind)` / `status_background(kind)` (success/warning/danger/info/neutral, có bản tối).
- Màu mặc định dự án `#0078D4`, không `Qt.GlobalColor.blue`.

## 5. Bố cục
- Banner tiêu đề có `QSizePolicy.Maximum` dọc; dialog có nội dung ngắn dùng `fit_dialog_to_content(self)` thay vì
  `resize(w, h)` cố định (khoảng trống lớn / banner bị kéo giãn).
- Nhiều checkbox tùy chọn ⇒ lưới nhiều cột (`QGridLayout`), không dồn một hàng ngang (bị cắt chữ).
- `QTabWidget` ⇒ `style_tab_widget()`; `QGroupBox` ⇒ `style_group_box()`; `QTableWidget` thô ⇒ `style_plain_table()`
  (nhớ đặt `verticalHeader().setDefaultSectionSize()` khi ô chứa LineEdit/nút).
- Không emoji trên khung giao diện (nút, tab, tiêu đề, label, combo): dùng `FluentIcon`. Nội dung hướng dẫn (QTextBrowser) được phép.

## 6. Test kiểm tra cắt chữ cần font thật
- Nền `offscreen` không có font ⇒ số đo sai. Test "không cắt chữ" tự skip khi offscreen; chạy file test trên nền tảng thật
  (không đặt `QT_QPA_PLATFORM`) để kiểm đủ 8/8.
