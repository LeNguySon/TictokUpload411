# Instinct 046: Browser Launch — Fail Closed, Real VPN Bridge, argv Hygiene

Kiểm toán phần quản lý trình duyệt (phòng thủ: vòng đời + chặn rò IP; KHÔNG nâng cấp khả năng né phát hiện).
Test: `tests/unit/test_browser_launch_safety.py`.

## 1. Không bao giờ mở trình duyệt từ IP máy thật
- `OrbitaLaunchWorker`: từ chối (emit `profile_failed`, không gọi SDK lẫn binary) khi hồ sơ không có proxy/VPN,
  proxy `leak_detected`, hoặc proxy không phản hồi. "Pre-launch guard" trước đây chỉ log cảnh báo.
- `OrbitaLauncher.launch_profile`: lớp thứ hai — không có proxy hợp lệ ⇒ `PermissionError`.
- Lỗi khởi động cầu nối VPN ⇒ `RuntimeError`, KHÔNG fallback mở trực tiếp (trước đây mở không proxy).

## 2. Cầu nối WireGuard
- Production không dùng `mock_mode` (mock chỉ giữ cổng, trình duyệt không có mạng). Binary: biến môi trường
  `TAVM_WG_BRIDGE_BINARY` hoặc `bin/wireproxy.exe` (`resolve_vpn_bridge_binary`). Không có ⇒ báo lỗi rõ ràng.
- File cấu hình tạm (chứa PrivateKey) bị xóa ngay sau khi daemon mở cổng / start lỗi.
- stdout/stderr của daemon = DEVNULL (pipe không ai đọc sẽ đầy và treo daemon).

## 3. argv dạng list không đi qua shell
- Không đặt dấu `"` trong giá trị cờ (`--host-resolver-rules="..."` ⇒ Chromium nhận chuỗi có ngoặc, bỏ qua luật chặn DNS).

## Ngoại lệ có chủ đích: chạy không proxy (2026-11-05)
- Cột `profiles.direct_connection` (0/1). Chỉ hồ sơ = 1 (người dùng xác nhận qua menu "Chạy không proxy (dùng IP máy)"
  hoặc mục cuối của AssignProxyDialog) mới được mở bằng IP máy; worker + launcher đều kiểm tra.
- Gán proxy/VPN (`bulk_assign_proxy`, `bulk_update_fields`) tự tắt cờ ⇒ mất proxy sau đó lại bị chặn (không lộ IP âm thầm).
- Cờ KHÔNG vượt qua proxy chết / `leak_detected`. Khởi chạy qua SDK ở chế độ trực tiếp ghi `proxy.mode=none` vào
  Preferences daemon để không dùng lại proxy cũ. Test: `tests/unit/test_direct_connection_profiles.py`.
