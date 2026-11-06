# Instinct 057: Gia hạn phiên / cookie TikTok (2026-11-06)

## Sự thật cần nhớ
- Hạn phiên do máy chủ TikTok quyết định. Sửa `expires` trong file cookie KHÔNG kéo dài phiên. Gia hạn = mở hồ sơ
  để TikTok tự làm mới phiên, rồi LƯU phiên mới.
- Chrome/Orbita mã hóa cookie nó ghi ⇒ đọc file SQLite khi trình duyệt đã đóng không lấy được phiên mới.
  Đọc qua DevTools của trình duyệt đang mở: `src/infrastructure/browser/cdp_session.py` (`Storage.getCookies`).

## Kiến trúc
- `CookieSessionService.capture(profile_id, debugger_addr)` → `cookies_browser`, `session_expires_at`,
  `cookies_synced_at`; không bao giờ ghi đè `cookies_json` (cookie người dùng nhập).
- Đọc phiên: định kỳ 10 phút cho mọi phiên SDK đang mở (`_capture_open_sessions`), và trước khi đóng (`_on_close_orbita`).
- "Làm mới phiên đăng nhập / gia hạn cookie" (menu Proxy & Mạng) → `SessionRefreshWorker`: mở qua
  `OrbitaLaunchWorker` (giữ nguyên cổng proxy), mở tab tiktok.com, chờ, capture, đóng (hồ sơ đang mở thì không đóng).
- Nguồn cookie duy nhất: `src/domain/policies/cookie_source.pick_session_cookie` (browser trước, import sau).
  Nhập cookie mới (`cookies_json`) ⇒ repo xóa `cookies_browser` và đặt `session_expires_at` theo cookie JSON.
- Cookie JSON giữ hạn thật; cookie đã hết hạn không được nạp. Cột "Cookie" hiện "Còn N ngày" / "Hết hạn" (cam < 7
  ngày, đỏ khi hết hạn) — không bao giờ hiện giá trị cookie.

## Kiểm chứng
- `tests/unit/test_session_renewal.py` (21 test), `scratch/perf/e2e_session_capture.py <chrome.exe>` ⇒ PASS với Chrome thật.
- In tiếng Việt ra console Windows: đặt `PYTHONIOENCODING=utf-8`.
