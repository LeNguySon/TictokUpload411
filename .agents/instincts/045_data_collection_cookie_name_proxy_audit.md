# Instinct 045: Data Collection Audit — Cookies, Profile Name, DB Connections, Avatar Proxy

Kiểm toán offline (không gọi TikTok). Test: `tests/unit/test_data_collection_audit.py`.

## 1. Cookie: hai cột, một định dạng
- `cookies_json` = cookie **người dùng nhập** (import/bulk/dialog). `cookies_browser` = cookie **đọc từ trình duyệt**.
  Cả hai lưu dạng chuỗi header `name=value; name2=value2` (mọi bộ đọc đều parse kiểu này).
- `sync_profile_offline_cookies` **không bao giờ ghi `cookies_json`**; chỉ ghi `cookies_browser` khi tìm thấy `sessionid`.
- Chrome/Orbita (≥ 80) mã hóa giá trị cookie vào `encrypted_value`, cột `value` rỗng. Chỉ có cookie mã hóa ⇒
  **không kết luận** (không đổi status/cookie). Trước đây ⇒ đánh DIE + ghi đè cookie người dùng bằng `{}`.
- DIE chỉ khi đọc được cookie TikTok dạng rõ mà không có session.

## 2. `name` là nhãn của người dùng
- Handle TikTok ghi vào `username_on_tiktok`. Sniffer chỉ điền `name` khi rỗng hoặc còn là tên tự sinh
  `Profile_{uuid[:8]}` (`_AUTO_PROFILE_NAME`).

## 3. Kết nối DB trong tầng thu thập
- Không dùng `sqlite3.connect` trần (timeout 5 s, không WAL/FK). Dùng `get_db_connection()` (busy_timeout 10 s) hoặc
  `db_session()`. Đã sửa `TikTokModerationService` và `GoLoginTikTokClient`.

## 4. Mọi request tới TikTok (kể cả CDN avatar) đi qua proxy của profile
- `avatar_cache_service._http_get(url, proxy_url)`; không có proxy hợp lệ / proxy `leak_detected` ⇒ bỏ qua, không gửi gì.
  urllib không tunnel được SOCKS ⇒ không fallback kết nối trực tiếp.

## 5. Môi trường
- `curl_cffi` (khai báo trong requirements) **chưa cài trong `.venv`** tại thời điểm kiểm toán: mọi lời gọi Creator API
  (`GoLoginTikTokClient.request_api`, moderation) ném `ModuleNotFoundError`, bị bắt và chỉ log `debug` ⇒ đồng bộ sâu
  âm thầm không chạy. Kiểm tra `pip show curl_cffi` khi thấy số liệu không cập nhật.
- Quy ước `privacy` chưa thống nhất: bộ thu thập ghi 1 = riêng tư / 0 = công khai, schema mặc định 1, dialog sửa
  hàng loạt ghi chuỗi "PUBLIC"/"PRIVATE".
