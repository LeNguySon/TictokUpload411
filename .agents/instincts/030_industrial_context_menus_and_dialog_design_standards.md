# Instinct 030: Tiêu Chuẩn Menu Ngữ Cảnh Cây Phân Cấp & Đồng Bộ Thiết Kế Dialog Công Nghiệp (Windows 11 Fluent)

## Bối Cảnh (Context)
- Ban đầu, bảng hồ sơ `ProfileTableWidget` sở hữu menu chuột phải dạng danh sách phẳng quá dài gồm 22 mục liên tiếp kéo dài cả màn hình, gây rối mắt và khó thao tác.
- Hệ thống 19 dialogs trong `src/presentation/dialogs/` thiếu quy chuẩn chung: phần lớn không đặt lề layout (`setContentsMargins`), thiếu banner tiêu đề trực quan, và một số dialog (như `AccountHealthDialog`) vẫn còn dùng nút `QPushButton` nguyên bản của Qt với CSS màu cứng inline.
- Các unit test khi mock `QDialog.exec` bằng `unittest.mock.patch("....Dialog.exec")` dễ bị treo hiển thị cửa sổ modal trên Windows nếu lớp con không khai báo rõ ràng phương thức `def exec(self): return super().exec()` trong Python.

## Giải Pháp Kỹ Thuật Chuẩn Hóa (Standardized Engineering Solutions)

### 1. Kiến Trúc Menu Chuột Phải Cây Phân Cấp (Hierarchical Context Menu)
- **Cấp gốc (Root Menu)**: Chỉ giữ tối đa 4 thao tác trực tiếp thường dùng nhất (`Mở Trình Duyệt`, `Đóng Trình Duyệt`, `Nạp Video Vào Hàng Đợi`, `Chuyển Vào Thùng Rác`).
- **5 Nhóm Cây Con (Submenus)** thông qua `RoundMenu`:
  - `Sức Khỏe & Kênh TikTok` (`FluentIcon.HEART`): Cookie, Đồng bộ số liệu, Gậy vi phạm, Radar, Cập nhật kênh, Mở trang TikTok web.
  - `Quản Lý Proxy & Mạng` (`FluentIcon.WIFI`): Gán proxy, Xoay IP, Kiểm tra Ping, Gỡ bỏ proxy / WireGuard.
  - `Quản Lý Hồ Sơ` (`FluentIcon.SETTING`): Chỉnh sửa hồ sơ, Chuyển vào dự án, Mở thư mục máy tính.
  - `Sao Chép Thông Tin` (`FluentIcon.COPY`): Copy ID, TikTok ID, Proxy, Cookie.
  - `Đổi Trạng Thái` (`FluentIcon.TAG`): LIVE, DIE, CHECKPOINT, stopped.
- **Biểu tượng (Icon)**: 100% sử dụng vector SVG `qfluentwidgets.FluentIcon` độ phân giải cao (High-DPI), loại bỏ toàn bộ emoji text tiền tố (`🛡️`, `📋`, `🏷️`).
- **Lưu ý kiểm thử `RoundMenu`**: Trong `qfluentwidgets.RoundMenu`, `menu.addMenu(sub)` lưu các menu con vào thuộc tính `_subMenus`, không thêm vào `actions()`. Do đó, khi kiểm tra toàn diện actions trong test cần duyệt đệ quy qua `getattr(menu, "_subMenus", [])`.

### 2. Tiện Ích Thiết Kế Dialog Chuẩn (`dialog_helpers.py`)
- Mọi dialog bắt buộc áp dụng:
  - Lề layout: `layout.setContentsMargins(20, 18, 20, 18)` (hằng số `STANDARD_DIALOG_MARGINS`).
  - Khoảng cách: `layout.setSpacing(12)` (hằng số `STANDARD_DIALOG_SPACING`).
  - Banner tiêu đề: `create_dialog_header(icon, title, subtitle, parent)` chứa vector `IconWidget(28x28)`, tiêu đề nổi bật 15px in đậm, và mô tả chức năng 12px thích ứng sáng/tối.
  - Nút bấm: 100% sử dụng `PrimaryPushButton` (cho hành động chính có kèm icon) và `PushButton` (cho nút Đóng/Hủy). Tuyệt đối cấm sử dụng `QPushButton` thô.

### 3. Khai Báo `def exec(self)` Trong Lớp Con QDialog
- Để đảm bảo khả năng kiểm thử tự động (Unit Test Mocking) với `unittest.mock.patch("....Dialog.exec")`, mọi lớp `QDialog` bắt buộc phải có phương thức:
  ```python
  def exec(self) -> int:
      """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
      return super().exec()
  ```
  giúp Python runtime không bỏ sót việc định tuyến mock khi chạy headless test suite.
