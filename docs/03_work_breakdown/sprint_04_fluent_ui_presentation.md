# Sprint 4: Giao Diện Người Dùng Windows 11 Fluent UI

- **Thời lượng dự kiến:** Tuần 4
- **Mục tiêu chính:** Xây dựng giao diện ứng dụng desktop Windows 11 chuẩn mực với `PyQt-Fluent-Widgets`, kiến trúc Model/View ảo hóa hiệu năng cao cho 2 bảng dữ liệu và hệ thống hộp thoại tương tác.

---

### `TSK-13-UI-SHELL`: Xây Dựng MainWindow Shell & Theme Manager
- **Loại hình:** Giao diện / Presentation Core
- **Tiền đề:** `TSK-01-ENV`
- **Mô tả công việc:**
  1. Tạo cửa sổ chính `MainWindow` kế thừa `FluentWindow`:
     - Thanh điều hướng bên trái (`NavigationInterface`): Các mục "Tài khoản", "Hàng đợi Video", "Cài đặt".
     - Thanh công cụ phía trên (`CommandBar`): Các nút thao tác nhanh.
     - Thanh trạng thái phía dưới (`QStatusBar`): Hiển thị trạng thái kết nối CSDL, số lượng profiles, tình trạng worker.
  2. Tích hợp bộ quản lý chủ đề (`ThemeManager`):
     - Chuyển đổi giữa chế độ Sáng (`Light`) và Tối (`Dark`).
     - Tự động nhận diện theme hệ thống của Windows 11.
     - Bật hiệu ứng Mica/Acrylic khi phần cứng và hệ điều hành hỗ trợ.
- **Đầu ra bàn giao:**
  - `presentation/windows/main_window.py`
  - `presentation/pages/settings_page.py`
  - Unit test `tests/ui/test_main_window.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Khởi chạy cửa sổ chính mượt mà, chuyển đổi trang điều hướng không bị nhấp nháy.
  - [ ] Chuyển đổi Theme Sáng/Tối tức thời mà không cần khởi động lại ứng dụng.

---

### `TSK-14-UI-ACC-PAGE`: Xây Dựng AccountsPage & TableModel Ảo Hóa
- **Loại hình:** Giao diện / Bảng dữ liệu
- **Tiền đề:** `TSK-03-REPO`, `TSK-10-WORKER-BASE`, `TSK-13-UI-SHELL`
- **Mô tả công việc:**
  1. Xây dựng `AccountTableModel` kế thừa `QAbstractTableModel`:
     - Lưu trữ danh sách profiles trong bộ nhớ, chỉ render các ô nhìn thấy trên màn hình.
     - Cung cấp dữ liệu định dạng cho các cột: Tên, TikTok ID, Followers, Views, Trạng thái.
  2. Xây dựng Custom Delegates:
     - `BadgeDelegate`: Vẽ `InfoBadge` Fluent cho trạng thái LIVE / DIE / CHECKPOINT.
     - `AvatarDelegate`: Vẽ ảnh đại diện bo tròn kèm placeholder icon.
  3. Xây dựng thanh công cụ tìm kiếm và lọc:
     - Ô tìm kiếm text có debounce 250ms để không truy vấn CSDL liên tục khi đang gõ.
     - Dropdown lọc theo Dự án (Project) và Trạng thái (Status).
  4. Menu ngữ cảnh chuột phải (Context Menu) với đầy đủ các lệnh.
- **Đầu ra bàn giao:**
  - `presentation/pages/accounts_page.py`
  - `presentation/models/account_table_model.py`
  - `presentation/delegates/badge_delegate.py`
  - `presentation/delegates/avatar_delegate.py`
  - Unit test `tests/ui/test_accounts_page.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Nạp 1,000 dòng dữ liệu mẫu: Thao tác cuộn chuột mượt mà, không giật khung hình.
  - [ ] Tích hợp Slot nhận `sig_sync_profile_done`: Dòng dữ liệu được cập nhật chỉ số tức thì mà không cần nạp lại toàn bộ bảng.

---

### `TSK-15-UI-QUEUE-PAGE`: Xây Dựng UploadQueuePage & Progress Delegate
- **Loại hình:** Giao diện / Hàng đợi
- **Tiền đề:** `TSK-09-UPLOAD-SVC`, `TSK-10-WORKER-BASE`, `TSK-13-UI-SHELL`
- **Mô tả công việc:**
  1. Xây dựng `QueueTableModel` kế thừa `QAbstractTableModel`:
     - Quản lý danh sách các tệp video trong hàng đợi `tiktok_queue`.
  2. Xây dựng `ProgressDelegate`:
     - Vẽ thanh tiến độ (`QProgressBar` kiểu Fluent) trực tiếp vào ô của cột "Tiến độ".
  3. Xây dựng thanh điều khiển hàng đợi:
     - Nút "Bắt đầu hàng đợi", "Tạm dừng", "Hủy job", "Xóa video đã hoàn tất".
  4. Kết nối tín hiệu đa luồng:
     - Slot tiếp nhận `sig_upload_progress`: Cập nhật trực tiếp giá trị % vào model.
     - Slot tiếp nhận `sig_upload_finished`: Đổi trạng thái badge sang `Done`, gắn mã publish ID.
- **Đầu ra bàn giao:**
  - `presentation/pages/upload_queue_page.py`
  - `presentation/models/queue_table_model.py`
  - `presentation/delegates/progress_delegate.py`
  - Unit test `tests/ui/test_queue_page.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Khi worker phát tín hiệu tiến độ %, thanh progress bar trên dòng tương ứng tăng mượt mà.
  - [ ] Nhấn nút "Tạm dừng" hoặc "Hủy" gửi đúng tín hiệu tới worker pool.

---

### `TSK-16-UI-DIALOGS`: Xây Dựng Hệ Thống Hộp Thoại (Dialogs)
- **Loại hình:** Giao diện / Hộp thoại
- **Tiền đề:** `TSK-13-UI-SHELL`
- **Mô tả công việc:**
  1. `AddProfileDialog`: Form thêm 1 tài khoản mới (Tên, Dự án, Proxy, Ghi chú).
  2. `BatchImportDialog`: Hộp thoại import danh sách profile từ Clipboard hoặc tệp CSV/TXT, hiển thị bảng xem trước (Preview Table) kèm thông báo lỗi định dạng trước khi bấm Xác Nhận.
  3. `VideoConfigDialog`: Hộp thoại thêm video vào hàng đợi:
     - Cho phép chọn nhiều file video `.mp4`, `.mov`.
     - Chọn tài khoản đích (hoặc gán tự động xoay vòng cho nhiều profile).
     - Soạn Caption kèm hỗ trợ chèn template tags.
     - Chọn quyền riêng tư (Public / Friends / Private).
     - Thiết lập khung giờ lên lịch đăng.
- **Đầu ra bàn giao:**
  - `presentation/dialogs/add_profile_dialog.py`
  - `presentation/dialogs/batch_import_dialog.py`
  - `presentation/dialogs/video_config_dialog.py`
  - Unit test `tests/ui/test_dialogs.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Tất cả dialog đều kế thừa `MessageBoxBase` của Fluent Widgets để đảm bảo tính thẩm mỹ cao.
  - [ ] Kiểm tra tính hợp lệ dữ liệu (Validation) trước khi cho phép bấm nút Submit (báo đỏ nếu để trống trường bắt buộc).

