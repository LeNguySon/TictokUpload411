# Instinct 033: Dual-Mode TikTok Upload and Business Status Code Trapping

## 1. Bản Chất Kỹ Thuật (Architecture & Context)
- Trong TikTok Web API (`/tiktok/web/project/post/v1/`), server ByteDance luôn trả về HTTP 200 OK ngay cả khi bài đăng bị từ chối nghiệp vụ.
- **Quy tắc bắt lỗi bắt buộc trong `TikTokHybridApiUploader`**:
  - `status_code == 0`: Xuất bản Aweme thành công.
  - `status_code == 4`: Máy chủ tạm thời bận (`Server is currently unavailable`).
  - `status_code == 8`: Phiên đăng nhập hết hạn (`Login expired`).
  - `status_code == 403 / 10000`: Thách thức bảo mật / CAPTCHA.
  - Điều kiện V8 Hybrid thành công duy nhất: `http_status == 200 and root_code == 0 and v8_result.get("ok", False)`.
- Mọi trường hợp `root_code != 0` đều phải được bẫy log chi tiết và tự động fallback sang `TikTokHeadlessStudioUploader` kèm đầy đủ tham số `schedule_time` để đảm bảo video luôn được xuất bản an toàn qua giao diện web DOM.

## 2. Tiêu Chuẩn Nạp Cookie Trình Duyệt GoLogin
- Trước khi khởi động trình duyệt hoặc thực thi V8 Fetch, nạp đồng thời:
  1. Ghi tệp SQLite Chromium `Network/Cookies` tại thư mục profile.
  2. Gửi lệnh CDP `Network.setCookies` ngay sau khi phiên trình duyệt mở cổng kết nối.
  Điều này bảo đảm session đăng nhập của tài khoản luôn sẵn sàng 100% trên cả tab và các service worker ngầm.

