# Instinct 040: Real Account Telemetry Verification, AgentShield Guard & Avatar Caching

## Bối Cảnh
Khi triển khai kiểm thử trực tiếp trên các tài khoản TikTok thực tế (Real Accounts: Profile #25 `@david.martin9472` và Profile #27 `@jayla.river29`):
1. **Rủi ro rò rỉ IP Host máy chủ**: Proxy được gán trong database có thể gặp lỗi kết nối hoặc HTTP 407 (Proxy Authentication Required / hết hạn gói cước / cần whitelist IP). Nếu client tự ý gửi request trực tiếp từ Host IP (`58.187.76.153`), tài khoản TikTok sẽ bị checkpoint hoặc thu hồi cookie đăng nhập (`sessionid`).
2. **QApplication Precedence & Native 0xC0000005 Access Violation**: Trên Windows PyQt6/PySide6, việc khởi tạo các module hoặc dịch vụ trước khi gọi `QApplication.instance() or QApplication(sys.argv)` hoặc không dừng các `QTimer` (`scheduler_timer`, `profile_status_timer`) khi kết thúc script kiểm thử sẽ gây crash bộ nhớ `0xC0000005`.

## Giải Pháp Kỹ Thuật (Industrial Standards)
1. **AgentShield Proxy Guard Enforcement**:
   - Mọi request Creator Center API qua `GoLoginTikTokClient` và `PassiveTikTokSyncService` đều buộc phải định tuyến qua proxy gán cho từng profile.
   - Khi proxy gặp lỗi (ví dụ HTTP 407), hệ thống ghi nhận log chẩn đoán, kích hoạt cơ chế phòng thủ không phát tán traffic qua IP thật của máy chủ.
   - Quá trình đồng bộ thoái lui an toàn (Fault-Tolerant): Vẫn hoàn tất việc tải ảnh đại diện về bộ đệm cục bộ (`data/avatars/<profile_id>.jpg`), lưu trữ `avatar_path` vào SQLite, và cập nhật dấu thời gian `statistic_date_update`.
2. **QApplication Lifecycle & Clean Shutdown Protocol**:
   - Luôn khởi tạo `QApplication` đầu tiên tại hàm `main()` của các script kiểm thử.
   - Trước khi đóng tiến trình, bắt buộc phải dừng tất cả timer và đợi `QThreadPool` xả hết tác vụ:
     ```python
     win.thread_pool.pool.waitForDone(5000)
     win.scheduler_timer.stop()
     if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
         win.profile_status_timer.stop()
     win.close()
     ```
3. **Local Avatar Caching Pipeline**:
   - `avatar_cache_service.download_and_cache_avatar()` lưu ảnh về thư mục đệm cục bộ và cập nhật đường dẫn tuyệt đối vào cột `avatar_path` của bảng `profiles`.
   - `CircularAvatarDelegate` đọc ảnh từ đĩa cục bộ, cắt bo tròn mượt mà, giúp bảng UI hiển thị trực quan mà không bị độ trễ tải mạng.
