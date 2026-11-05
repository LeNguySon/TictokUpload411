# Instinct 043: AgentShield Strict Proxy Gate & Zero Host IP Leak

## Bối Cảnh
Trong các hệ thống quản trị tài khoản TikTok MMO quy mô lớn:
- Khi người dùng tạo profile mới hoặc import profile hàng loạt nhưng sơ ý chưa gán proxy (`proxy_id = None`).
- Nếu người dùng bấm "Bắt đầu đăng", "Đồng bộ số liệu" hoặc chạy lịch hẹn giờ, việc thiếu chốt chặn sẽ khiến client tự động kết nối trực tiếp đến TikTok từ **IP thật của máy chủ (Host IP)**.
- **Hậu quả thảm khốc**:
  1. **Lệch Geolocation & Thu hồi Session**: Tài khoản đang mang danh tính US/UK/DE bị gửi request mang `sessionid` từ IP Việt Nam khiến TikTok lập tức thu hồi cookie, biến trạng thái từ `LIVE` thành `DIE`.
  2. **Gom cụm Bot Farm (Cluster Shadowban)**: Hàng chục tài khoản khác nhau cùng gửi request từ 1 địa chỉ IP thật sẽ bị TikTok WAF gom thành bot farm và bóp tương tác toàn bộ kênh (0 view).

## Giải Pháp Kỹ Thuật (Phòng Thủ 3 Lớp Sâu)

### 1. Lớp 1: Presentation Gate (UI Fast-Fail)
- **Hàng đợi Upload (`_on_start_upload_queue`, `_on_upload_single_video`)**:
  - Tự động lọc danh sách profile được chọn: Phân tách `proxied_profiles` và `skipped_no_proxy`.
  - Nếu toàn bộ tài khoản được chọn không có proxy: Chặn đứng hoàn toàn và hiển thị `InfoBar.error` hướng dẫn người dùng gán proxy trước.
  - Nếu có một phần tài khoản thiếu proxy: Tự động bỏ qua các tài khoản đó, phát lệnh upload cho các tài khoản an toàn và hiển thị `InfoBar.warning` thông báo số lượng tài khoản được bảo vệ.
- **Đồng bộ Số liệu (`_on_sync_selected_metrics`)**:
  - Lọc bỏ các profile thiếu proxy trước khi gửi danh sách cho `MetricsSyncWorker`.
- **Mở Trình duyệt Orbita (`_on_launch_orbita`)**:
  - Hiển thị cảnh báo trực quan nếu profile chưa gán proxy để người dùng nhận thức rủi ro IP máy thật.

### 2. Lớp 2: Application / Service Gate (Execution Barrier)
- **`UploadService.execute_upload()`**:
  - Ngay sau khi xác thực profile tồn tại, kiểm tra nghiêm ngặt `proxy_id = profile_row.get("proxy_id")`.
  - Nếu profile không có proxy hoặc proxy bị gắn cờ `leak_detected`:
    - Ghi nhận `_safe_log("SECURITY", "CHẶN AN TOÀN AGENTSHIELD...", "ERROR")`.
    - Đánh dấu video là `failed` kèm thông điệp: `"Security: Profile chưa gán Proxy (Strict Proxy Gate)"`.
    - Ném `PermissionError` ngay lập tức để không bao giờ chạm đến tầng Adapter.
- **`MetricsSyncWorker.execute()`**:
  - Trước khi gọi `sync_metrics_from_tiktok`, kiểm tra `prof.get("proxy_id")`. Nếu rỗng hoặc proxy bị `leak_detected`, tự động bỏ qua và cập nhật tiến trình % mà không phát sinh request mạng.

### 3. Lớp 3: Infrastructure Gate (Zero-Leak Boundary)
- **`GoLoginTikTokClient.request_api()`**:
  - Nếu `_build_proxy_url(proxy_dict)` trả về `None`, ném `PermissionError("AgentShield Strict Proxy Gate: Outbound TikTok request blocked...")`.
  - Triệt tiêu 100% nhánh fallback nguy hiểm `proxies = None`.
- **`PassiveTikTokSyncService._fetch_url_content()`**:
  - Xóa bỏ hoàn toàn nhánh khởi tạo `urllib.request.build_opener()` không proxy. Nếu không có proxy hợp lệ, trả về `""` ngay lập tức.
