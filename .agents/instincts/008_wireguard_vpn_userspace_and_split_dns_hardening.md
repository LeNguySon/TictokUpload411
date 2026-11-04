# Instinct 008: Userspace WireGuard VPN Bridge & Anti-Split-DNS Hardening

## 1. Bản Chất Kỹ Thuật (Technical Root Cause)
- **Split DNS Leak Trong Chromium**: Khi cấu hình proxy cho Chromium bằng cờ thông thường, trình duyệt vẫn có thể sử dụng DNS nội bộ của Router/ISP để giải quyết IP trước khi chuyển kết nối vào kênh proxy, dẫn đến rò rỉ DNS địa phương (Split DNS leak).
- **Giải Pháp Triệt Để**: Bổ sung cờ `--host-resolver-rules="MAP * 0.0.0.0 , EXCLUDE <proxy_host>"` ép 100% yêu cầu DNS đi qua đường hầm proxy từ xa, ngoại trừ IP đích của chính proxy server. Đồng thời bổ sung `--enforce-webrtc-ip-permission-check`.

## 2. Đồng Bộ Hóa Vị Trí Địa Lý (Timezone, GeoIP, Language)
- Khi mở profile qua proxy hoặc WireGuard VPN, anti-bot TikTok sẽ so sánh IP egress với JavaScript runtime (`Intl.DateTimeFormat().resolvedOptions().timeZone` và `navigator.languages`).
- Hệ thống tự động trích xuất `timezone_id`, `latitude`, `longitude`, và `country` gán trực tiếp vào file cấu hình C++ `Default/Preferences` (`gologin.timezone`, `gologin.geoLocation`, `gologin.languages`), bảo đảm tính đồng nhất 100% giữa mạng và vân tay phần mềm.

## 3. Userspace WireGuard VPN Bridge Mỗi Profile
- Nhằm cho phép mỗi profile TikTok sở hữu một kết nối WireGuard riêng biệt mà không làm ảnh hưởng hoặc thay đổi cấu hình mạng toàn hệ thống (Windows Network Adapter / Routing Table), hệ thống khởi tạo `UserspaceVpnBridge` chuyển đổi WireGuard endpoint thành cổng SOCKS5 cục bộ (`127.0.0.1:<port>`).
- Khi đóng profile (`OrbitaLauncher.close_profile`), toàn bộ tiến trình cầu nối VPN được dọn dẹp sạch sẽ, không để lại zombie process.
