# Instinct 024: Kháng Cáo Video Vi Phạm, Tái Gia Nhập Quỹ Nhà Sáng Tạo & Tích Hợp GoLogin SDK Proxy Routing

## Bối Cảnh & Vấn Đề Thực Tế
1. **Kháng Cáo Video Vi Phạm & Gậy Nguyên Tác**:
   - Khi video bị thuật toán kiểm duyệt của TikTok gắn cờ gậy bản quyền hoặc gậy nguyên tác (ineligible for FYP/Rewards), người dùng cần có khả năng nộp đơn kháng nghị trực tiếp từ `AccountHealthDialog`.
   - Trạng thái video trong `violateVideos` phải chuyển sang `'appealed'` kèm `appeal_date`, đồng thời mở một vé theo dõi tương ứng trong `accountAppeals`.
2. **Kiểm Tra Tiến Độ & Nộp Lại Đơn Quỹ Sáng Tạo (Creator Rewards Re-application)**:
   - Khi tài khoản bị đình chỉ khỏi Quỹ Sáng Tạo, TikTok đặt thời hạn phạt `date_reapply`.
   - Trước thời hạn, hệ thống phải ngăn chặn việc nộp đơn sớm bằng đồng hồ đếm ngược trực quan (`days_left`).
   - Khi đến hạn, kích hoạt nút nộp lại đơn, gọi API và đưa trạng thái kênh về `Good` (`date_reapply = NULL`).
3. **Gọi TikTok API Qua GoLogin SDK Thay Vì Bare Requests**:
   - Việc gọi `requests.get("https://www.tiktok.com/passport/web/account/info/", ...)` trực tiếp từ IP máy chủ dễ bị TikTok chặn IP hoặc Cloudflare WAF checkpoint.
   - Bắt buộc phải thông qua `GoLoginTikTokClient`:
     - Tự động trích xuất proxy của profile (`host:port:user:pass`).
     - Tự động giải mã cookie nhạy cảm qua Windows DPAPI (`gloglin:dpapi:v1:`).
     - Định tuyến toàn bộ request qua đúng proxy và Chrome 120 TLS fingerprint của profile.

## Giải Pháp Kỹ Thuật
1. **Module `GoLoginTikTokClient`** (`src/infrastructure/tiktok/gologin_tiktok_client.py`):
   - `get_profile_cookie_header(profile_id)`: Trích xuất cookie từ database (giải mã DPAPI) hoặc truy vấn qua daemon GoLogin SDK.
   - `get_profile_proxy(profile_id)`: Đọc cấu hình proxy gán cho profile trong bảng `proxies`.
   - `request_api(profile_id, url, method, ...)`: Gửi request an toàn qua đúng proxy với đầy đủ CSRF tokens (`x-secsdk-csrf-token`).
   - `verify_session(profile_id)`: Kiểm tra phiên đăng nhập với TikTok Passport một cách an toàn.
2. **Nâng cấp `TikTokModerationService`** (`src/infrastructure/tiktok/moderation_service.py`):
   - Bổ sung `submit_video_appeal(profile_id, video_id, appeal_reason)`.
   - Bổ sung `submit_creator_rewards_reapply(profile_id)`.
   - Bổ sung `check_appeal_status(profile_id)`.
3. **Nâng cấp Giao diện `AccountHealthDialog`** (`src/presentation/dialogs/account_health_dialog.py`):
   - Thêm KPI Card & Banner đếm ngược thời gian phạt `card_reapply_countdown`.
   - Thêm nút `btn_reapply_creator` nộp lại đơn Quỹ Sáng Tạo.
   - Thêm nút `btn_appeal_video` kháng cáo video đang chọn với các mẫu lý do chuẩn.
   - Thêm nút `btn_check_appeals` kiểm tra tiến độ kháng cáo.
   - Toàn bộ thao tác network chạy trên background thread thông qua `QTimer` và `concurrent.futures`.

## Quy Tắc Bắt Buộc Cho Agent Sau
- Tuyệt đối không gọi bare `requests.get(...)` mà không có proxy routing cho các tác vụ TikTok Creator/Passport. Luôn dùng `GoLoginTikTokClient`.
- Khi cập nhật trạng thái `appealed` cho video, luôn cập nhật đồng thời cả hai bảng `violateVideos` và `accountAppeals` để đảm bảo tính toàn vẹn dữ liệu.
- Giữ vững nguyên tắc AgentShield: Cookie và mật khẩu proxy luôn được mã hóa/giải mã qua DPAPI, không bao giờ in plaintext vào log.

