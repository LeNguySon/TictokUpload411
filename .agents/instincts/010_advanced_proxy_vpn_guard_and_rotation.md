# Instinct 010: Advanced Proxy, WireGuard VPN Guard & Auto IP Rotation

## 1. Trực Quan Hóa Cấu Hình Mạng Trên Giao Diện Bảng (Visual Proxy/VPN Rendering)
- Hồ sơ gán WireGuard VPN hiển thị `🛡️ WireGuard VPN` (Col 4) và `WireGuard` (Col 5) giúp người dùng MMO phân biệt ngay lập tức giữa proxy HTTP/SOCKS5 thông thường và đường hầm mã hóa WireGuard độc lập.
- Hồ sơ sử dụng Proxy Xoay (Rotating Proxy) tự động gắn tiền tố `🔄` trước `host:port` để người dùng nhận diện proxy có khả năng đổi IP.

## 2. Tiền Kiểm Tra Proxy Trước Khi Khởi Chạy (Pre-launch Proxy Guard)
- Tránh việc mở trình duyệt Chromium khi mạng trung gian hoặc proxy server đã chết (`ERR_PROXY_CONNECTION_FAILED`), bằng cách kiểm tra nhanh kết nối TCP socket qua `_check_proxy_alive(proxy_data, timeout=1.5)`.
- Tự động kích hoạt URL xoay IP (`change_ip_url`) trước khi mở cửa sổ Orbita cho proxy xoay, bảo đảm phiên làm việc luôn bắt đầu bằng một IP mới sạch sẽ.

## 3. Thao Tác Chuột Phải Nhanh (Fast Context Actions)
- `_on_remove_proxy_selected`: 1-click gỡ bỏ cả `proxy_id` lẫn `vpn_config` trên hàng loạt hồ sơ đã chọn.
- `_on_rotate_proxy_selected`: 1-click gọi API đổi IP cho các proxy xoay.
- `_on_check_proxy_selected`: Kiểm tra trực tiếp trạng thái Live/Die và độ trễ ping của proxy và tự động làm mới giao diện.
