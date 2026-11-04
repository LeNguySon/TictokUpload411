# 003 — UI Dialogs, Orbita Browser Launcher & Full Interaction Parity Instincts

## Bối Cảnh & Vấn Đề (Context & Problem)
- Giao diện người dùng ban đầu tồn tại nhiều nút bấm chưa có dialog xử lý, hoặc chỉ hiển thị thông báo `InfoBar` giữ chỗ (mockup/placeholder).
- Thanh công cụ phía trên bị phân mảnh thành 2 hàng nút cồng kềnh, gây rối mắt và làm giảm diện tích hiển thị của bảng 28 cột MMO.
- Trình duyệt Orbita Antidetect cần cơ chế khởi chạy nền tách biệt với main GUI thread và tự động gán proxy, fingerprint noise.

## Bài Học & Giải Pháp Kỹ Thuật (Instincts & Solutions)

1. **Thiết Kế Tối Giản Windows 11 Fluent UI Bar**:
   - Thanh tiêu đề cấp cao chỉ giữ lại 3 thành phần cốt lõi:
     - `Dự án: ComboBox`: Phân nhóm và lọc hồ sơ theo chiến dịch.
     - `Tìm kiếm: SearchLineEdit`: Lọc theo thời gian thực (tên, proxy, ID TikTok, email).
     - `⚙ Icon Cài Đặt (TransparentToolButton + RoundMenu)`: Tích hợp toàn bộ các tính năng mở rộng có phân nhóm rõ ràng (Hồ sơ TikTok, Quản lý Dự án & Proxy, Bảo mật & API, Bảo trì & Trợ giúp).
2. **Loại Bỏ Hoàn Toàn Placeholder/Mockup**:
   - Mọi nút bấm và menu action đều có Dialog chức năng thực tế:
     - `ApiCookieDialog`: Cấu hình client key, secret, lưu cookie dự phòng mã hóa DPAPI.
     - `PermissionsDialog`: Hỗ trợ quy trình OAuth 2.0 PKCE, sinh link ủy quyền và nhận mã xác thực.
     - `TableSettingsDialog`: Bật/tắt hiển thị động từng cột trong số 28 cột MMO qua `setColumnHidden`.
     - `ScheduleVideoDialog`: Thuật toán phân bổ so le (`generate_staggered_schedule`) kèm jitter ngẫu nhiên chống phát hiện spam.
     - `VideoMetadataDialog`: Chỉnh sửa tiêu đề, hashtag, chế độ riêng tư (Public/Friends/Self) và cờ duet/stitch.
     - `SyncTransferDialog`: Đóng gói hồ sơ và proxy ra `.zip` và khôi phục CSDL an toàn kèm giải quyết ràng buộc khóa ngoại (Foreign Key fallback).
     - `UserGuideDialog`: Cung cấp tài liệu tra cứu nội bộ dạng Markdown chi tiết về 28 cột MMO, chống leak proxy và phím tắt.
3. **Orbita Antidetect Process Isolation**:
   - `OrbitaLauncher` tự động quét đường dẫn Chrome/Orbita trong GoLogin profile directory, thiết lập fingerprint canvas noise, webrtc leak protection và proxy server flag.
   - Khởi chạy qua `subprocess.Popen` async, không block PyQt6 GUI thread.
4. **An Toàn Khóa Ngoại SQLite Khi Nhập Dữ Liệu Ngoại Lai**:
   - Khi import profile từ file zip, luôn ánh xạ hoặc cho phép fallback `project_id=None`, `proxy_id=None` nếu bản ghi dự án hoặc proxy gốc không tồn tại ở CSDL mới, tránh lỗi `FOREIGN KEY constraint failed`.

