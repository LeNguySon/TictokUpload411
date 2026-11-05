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
