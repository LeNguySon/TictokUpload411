# Instinct 037: Proxy Binding & Leak Prevention in Data Collection

## Bối Cảnh
Trong các hệ thống quản trị tài khoản TikTok MMO quy mô lớn, việc thu thập dữ liệu (Data Collection, Creator Metrics, DOM Hydration, Account Standing) nếu thực hiện từ IP thật của máy chủ (Host IP) sẽ gây ra các hậu quả nghiêm trọng:
1. **Lệch Geolocation & Revoke Session**: Profile đang chạy proxy US/DE nhưng request API số liệu lại xuất phát từ IP Việt Nam khiến TikTok thu hồi `sessionid`, biến tài khoản từ `LIVE` thành `DIE`.
2. **Liên đới mạng (Cluster Linkage)**: Tất cả tài khoản gửi request từ 1 IP duy nhất sẽ bị gom thành bot farm và bị shadowban đồng loạt.
3. **Lộ IP máy chủ**: Direct Post API ghi nhận IP truy vấn trong Partner Audit Log.

## Giải Pháp Kỹ Thuật (AgentShield Standard)
1. **Tầng SDK (`TikTokDirectPostClient`)**:
   - Mọi phương thức truy vấn (`query_creator_info`, `init_direct_post`, `upload_video_chunks`, `get_post_status`) nhận tham số `proxy_url: Optional[str] = None`.
   - Cấu hình `proxies={"http": proxy_url, "https": proxy_url}` trực tiếp vào `requests.Session.post/get/put`.
2. **Tầng Adapter (`SamMonnyTikTokAdapter`)**:
   - `fetch_creator_metrics(profile_id)` tự động tra cứu `proxy_id` của profile trong `ProfileRepository`.
   - Nếu proxy có trạng thái `leak_detected`, ném `PermissionError` ngăn chặn khẩn cấp.
   - Định dạng proxy URL chuẩn RFC (`format_proxy_url`) và truyền xuống SDK client.
3. **Tầng Passive Scraping (`PassiveTikTokSyncService`)**:
   - Kiểm tra `leak_detected` ngay tại đầu vào `_fetch_url_content`, từ chối tạo `urllib.request.build_opener()` nếu proxy bị tainted.
4. **Tầng Worker (`MetricsSyncWorker`)**:
   - Sử dụng `_safe_emit` bọc mọi lệnh phát tín hiệu Qt (`profile_updated`, `progress`), triệt tiêu `RuntimeError` khi đóng ứng dụng.

