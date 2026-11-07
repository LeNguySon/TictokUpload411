# 074 — Vân tay + proxy cố định trong mọi thao tác (kiểm chứng ngày 2026-11-07, profile 78)

## Đã đo trên tài khoản thật
- **Proxy:** mọi request (API, sync, kiểm tra vi phạm, avatar, trang) và cả trình duyệt đều đi đúng proxy của profile (instinct 070, 071).
- **Trình duyệt:** mở 2 lần cho kết quả giống nhau.
  - UA Chrome/139, WebGL Intel UHD 620, màn hình 1920×1080, 12 nhân CPU, múi giờ Asia/Bangkok, ngôn ngữ vi.
  - Hash canvas `271c40f1` giống nhau ở cả 2 lần.
  - Khớp `fingerprint_json` trong app và bản ghi trong daemon.
- **App và daemon:** 19 profile có bản ghi daemon đều cùng UA. 48 profile chỉ có ở local được khởi chạy bằng chính vân tay của app.

## Lỗi đã sửa: request của app tự khai là trình duyệt khác
- Creator API: TLS Chrome 120 + `en-US`. curl_cffi còn tự thêm `sec-ch-ua` v136 và `sec-ch-ua-platform: "macOS"` vào một UA Windows.
- Tải avatar: Chrome 123. Lấy trang (DOM): Chrome/152 + `en-US`.
- Cách sửa: `browser_identity.request_identity(profile)` → UA của vân tay, `sec-ch-ua` cùng major, nền tảng lấy từ `navigator.platform`, Accept-Language lấy từ `navigator.languages`, và TLS = bản Chrome desktop curl_cffi gần nhất không mới hơn UA (139 → chrome136).
- Live: Creator API trả 200 / `status_code` 0 với danh tính mới.

## Còn lại (cần làm trong SDK)
- Hybrid VOD (`TikTokVODClient`) gửi ApplyUploadInner kèm cookie tài khoản bằng `requests` (TLS của Python) và UA/sec-ch-ua GÁN CỨNG Chrome/139. Nên nhận UA thật của trình duyệt (CDP `navigator.userAgent`) và dùng curl_cffi impersonate.
- 3 profile local có vân tay Chrome 124: trình duyệt chạy bằng lõi Orbita khác phiên bản, nên TLS của lõi ≠ UA khai báo.
