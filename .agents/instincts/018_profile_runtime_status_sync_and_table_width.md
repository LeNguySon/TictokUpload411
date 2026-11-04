# Bản Năng Kỹ Thuật: Đồng Bộ Thời Gian Thực Tình Trạng Profile & Độ Rộng Cột Tránh Cắt Chữ

## Bối cảnh & Nguyên nhân gốc rễ
1. Cột `Tình trạng` (Cột 12 trong `ProfileTableWidget`) trước đây bị cố định ở độ rộng `80px`. Khi hiển thị trạng thái `stopped` hoặc `running`, do padding của ô bảng và font chữ, chuỗi ký tự bị cắt ngắn thành `stop...`.
2. Khi người dùng mở hoặc đóng trình duyệt Orbita qua menu ngữ cảnh hoặc thanh công cụ, `_on_orbita_profile_launched` và `_on_close_orbita` chỉ gửi lệnh/ghi log mà chưa cập nhật trạng thái `running` / `stopped` vào CSDL SQLite và chưa gọi `refresh_profiles()`.
3. Khi người dùng tự tắt cửa sổ Chromium bằng tay, hệ thống thiếu hàm `is_profile_running` để tự động đối soát trạng thái tiến trình thực tế trên hệ điều hành so với CSDL.
4. Trong PySide6 / QFluentWidgets, gọi `setTheme` nhiều lần trong vòng đời kiểm thử khi các widget cũ đã bị hủy C++ wrapper sẽ gây OS Access Violation do StyleSheetManager duyệt weak reference. Cần bảo vệ bằng `isDarkTheme()` hoặc exception handling.

## Giải pháp kiến trúc đã thực thi
1. **Mở rộng độ rộng cột 12 lên 110px**:
   - `self.setColumnWidth(12, 110)` đảm bảo hiển thị đầy đủ và thoải mái mọi trạng thái (`running`, `stopped`, `LIVE`, `DIE`, `CHECKPOINT`).
   - Thiết lập màu sắc Fluent UI chuẩn: `running` dùng xanh dương đậm (`#0078D4`, font in đậm Bold), `stopped` dùng xám trung tính (`#605E5C`).
2. **Bổ sung `is_process_running` vào `BrowserProcessSupervisor`**:
   - Kiểm tra lock file `.process.lock` và tính hợp lệ của PID qua `psutil.pid_exists(pid)`.
3. **Bổ sung `is_profile_running` vào `OrbitaLauncher`**:
   - Kiểm tra tiến trình bộ nhớ active Popen (`proc.poll() is None`) và kiểm tra qua lock file supervisor.
4. **Vòng đời mở/đóng và tự động đối soát trong `MainWindow`**:
   - `_on_orbita_profile_launched`: Lưu `status = 'running'` vào DB và gọi `self.refresh_profiles()`.
   - `_on_close_orbita`: Đóng tiến trình, lưu `status = 'stopped'` vào DB và gọi `self.refresh_profiles()`.
   - `refresh_profiles()`: Tự động đối soát `self.orbita_launcher.is_profile_running(p)` với `db_status` để cập nhật trạng thái thực tế ngay lập tức.
5. **Phòng chống Access Violation trong Qt / QFluentWidgets**:
   - Thêm `self.clearSelection()` trước `setRowCount` trong bảng để tránh QItemDelegate updateEditorGeometry trên widget bị xóa.
   - Thêm kiểm tra `isDarkTheme()` trước khi gọi `setTheme(Theme.LIGHT)`.

