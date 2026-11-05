# Instinct 048: SonBetaPro Branding, Windows AppUserModelID & Multi-Resolution Icon Resolution

## Context
Người dùng yêu cầu đổi tên toàn bộ ứng dụng thành **SonBetaPro** và sử dụng `D:\TictokUpload411\icon.ico` làm icon của ứng dụng.

## Tri Thức Kỹ Thuật & Bài Học Thực Nghiệm

1. **Windows 11 Taskbar Grouping & AppUserModelID**:
   - Khi chạy ứng dụng Python PyQt trên Windows, mặc định hệ điều hành gán tiến trình vào `python.exe` và hiển thị icon mặc định của Python trên thanh Taskbar.
   - Để Windows 11 hiển thị đúng icon tùy chỉnh của ứng dụng trên Taskbar và gán tên nhóm ứng dụng riêng biệt, bắt buộc phải gọi hook Win32 API trước khi khởi tạo `QApplication`:
     ```python
     if sys.platform == "win32":
         import ctypes
         ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SonBetaPro.App.2026")
     ```

2. **QIcon Đa Độ Phân Giải (Multi-Resolution ICO)**:
   - Tệp `icon.ico` chứa 6 kích thước biểu tượng chuẩn Windows: `16x16`, `32x32`, `48x48`, `64x64`, `128x128`, `256x256`.
   - `QIcon` bắt buộc phải được khởi tạo sau khi `QApplication` đã tồn tại trên Windows.
   - Gọi cả `app.setWindowIcon(app_icon)` (để toàn bộ sub-dialogs tự động thừa kế) và `main_window.setWindowIcon(app_icon)` (để thanh tiêu đề cửa sổ chính hiển thị sắc nét).

3. **Cấu Hình `qt_api = "pyqt6"` Trong `pyproject.toml` Cho `pytest-qt`**:
   - Nếu môi trường cài đặt cả `PySide6` và `PyQt6`, plugin `pytest-qt` mặc định có thể tự động chọn `PySide6`. Khi đó, các widget PyQt6 đưa vào `qtbot.addWidget(widget)` sẽ ném lỗi:
     `TypeError: Need to pass a QWidget to addWidget: <...>`
   - Bắt buộc phải khai báo rõ trong `pyproject.toml`:
     ```toml
     [tool.pytest.ini_options]
     qt_api = "pyqt6"
     ```
   - Thiết lập này đảm bảo 100% test suite (407 bài test) chạy đồng nhất trên nhân `PyQt6`.

4. **Đường Dẫn Fallback Khả Chuyển (Portability)**:
   - Module `src.presentation.app_icon.get_app_icon()` giải quyết đường dẫn ứng dụng qua danh sách ưu tiên:
     1. Tuyệt đối: `D:/TictokUpload411/icon.ico`
     2. Gốc repo: `Path(__file__).resolve().parent.parent.parent / "icon.ico"`
     3. Tài nguyên đóng gói: `resources/icons/app_icon.ico`
     4. Thư mục làm việc hiện tại: `icon.ico`

