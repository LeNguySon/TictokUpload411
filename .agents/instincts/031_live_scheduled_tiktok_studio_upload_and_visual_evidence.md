# Instinct 031: Live Scheduled TikTok Studio Upload and Visual Evidence Standards

## 1. Bản Chất Kỹ Thuật (Architecture & Context)
- Quy trình hẹn giờ đăng video lên TikTok Studio Native Cloud yêu cầu tính toán mốc thời gian trong tương lai được làm tròn tới khoảng 5 phút gần nhất (ví dụ: `2026-11-05 16:50:00`), tránh xung đột với server-side scheduling gate của TikTok Studio.
- `UploadService.execute_upload` tiếp nhận `schedule_time: str | None`. Nếu có giá trị, nó được ưu tiên đóng gói vào `metadata["schedule_time"]` của draft và kích hoạt đường truyền TikTok Studio Cloud Native Scheduling.
- Tránh khóa/đơ giao diện (UI Freeze): Việc loại bỏ console drawer dưới đáy và chuyển toàn bộ thanh tiến trình đa luồng (0% -> 100%) cùng log nhật ký lỗi vào thẳng bảng `VideoQueueTableWidget` (cột 10 & 11) giúp loại bỏ triệt để hiện tượng đơ giao diện khi người dùng ẩn/thu gọn nhật ký.

## 2. Tiêu Chuẩn Báo Cáo Nghiệm Thu Bằng Hình Ảnh (Visual Evidence Standards)
- Khi thực thi kiểm thử giao diện hoặc luồng upload thực tế, sử dụng `widget.grab()` hoặc `widget.render(pixmap)` trong môi trường Qt High-DPI để xuất ảnh chụp sắc nét độ phân giải cao (`.png`).
- Tất cả ảnh minh chứng phải được lưu trữ trực tiếp tại thư mục artifact `C:\Users\sonson\.gemini\antigravity\brain\<conversation-id>/` và nhúng vào báo cáo nghiệm thu GATE 2 bằng cú pháp Markdown chuẩn:
  `![Chú thích](file:///C:/Users/sonson/.gemini/antigravity/brain/<conversation-id>/filename.png)`
- Bắt buộc kiểm tra chuỗi 3 mốc xác minh:
  1. **Staged Queue Image**: Hiển thị video đã nạp vào hàng đợi kèm cột "Lên lịch", trạng thái "Sẵn sàng" và tài khoản đích.
  2. **Completed Upload Image**: Hiển thị thanh tiến trình 100% màu xanh, trạng thái "Xuất bản thành công", và mã `Publish ID`.
  3. **Database & File Isolation Image**: Xác nhận bản ghi SQLite chuyển sang `published` và tệp video vật lý được cách ly an toàn vào thư mục `_posted/`.

