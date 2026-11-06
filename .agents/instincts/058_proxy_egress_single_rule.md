# Instinct 058: Một luật duy nhất cho đường ra mạng (egress) của tài khoản (2026-11-06)

## Luật
- Mọi request thay mặt một hồ sơ PHẢI đi qua `src/infrastructure/proxy/egress.resolve_profile_egress(profile, proxy)`:
  trả URL proxy; `None` chỉ khi người dùng bật "Chạy không proxy" (`direct_connection`); còn lại raise
  `EgressBlocked` (PermissionError, thông điệp "AgentShield Strict Proxy Gate: …"). Không bao giờ fallback đi thẳng.
- Bị chặn: không proxy (không opt-in), proxy `leak_detected` (kể cả khi đã opt-in), proxy hỏng/thiếu, hồ sơ chỉ có
  WireGuard (VPN chỉ cho trình duyệt).
- Dựng URL proxy chỉ bằng `build_proxy_url` (mã hóa user/pass, socks5 → `socks5h` để DNS phân giải qua proxy).
  Log URL proxy chỉ qua `redact_proxy_url`; `RedactionFilter` cũng che `scheme://user:pass@`.

## Lỗi đã vá (test: `tests/unit/test_proxy_egress.py`)
- Upload Direct Post chính thức: SDK gọi `init_direct_post`/`upload_video_chunks` KHÔNG truyền proxy ⇒ upload từ IP
  máy. `ProxyBoundDirectPostClient` (thread-local `bound(proxy_url)`) tiêm proxy; test chống SDK đổi tên hàm.
- Phiên trình duyệt upload, `fetch_creator_metrics`, nhánh dự phòng moderation, DOM scraping: đều qua resolver.
- Health check đọc `row["scheme"]` (không tồn tại) ⇒ SOCKS bị kiểm như HTTP. Cột đúng là `protocol`.
- Leak policy chỉ biết IP LAN ⇒ không bao giờ phát hiện proxy đi qua IP public của máy. `discover_public_ip()`
  lười (khi evaluate, trong worker), cache 30 phút; conftest chặn gọi mạng trong test.
- Parser: mật khẩu chứa `@`/`:`; cổng 1–65535; giao thức hợp lệ. `ProxyRepository.create` trả id thật khi trùng (trước: 0).

## Kiểm chứng
- `scratch/perf/e2e_proxy_egress.py`: proxy cục bộ ghi nhận request curl_cffi + lệnh SDK Direct Post thật, đúng
  user/pass có ký tự đặc biệt; hồ sơ không proxy không gửi byte nào ⇒ PASS.
