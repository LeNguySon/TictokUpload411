# Instinct 006: Passive Data Collection, Antidetect Proxy Preferences, and UI Live Sync

## 1. Bản Chất Kỹ Thuật (Technical Reality)
- Đối với $95\%$ tài khoản TikTok MMO (đăng nhập bằng Cookie hoặc trình duyệt Orbita), ứng dụng **không có OAuth 2.0 Access Token**.
- Không được bắt buộc phải có OAuth token để lấy số liệu kênh (tránh lỗi `No active access token in Windows Vault`).
- Thay vào đó, áp dụng **Kiến trúc Thu thập Dữ liệu Thụ động 3 Tầng**:
  1. **Tầng 1 (Live CDP Network Sniffer)**: Lắng nghe trực tiếp các gói tin phản hồi của TikTok API (`/api/user/detail`, `/api/creator/dashboard/overview`, `/api/post/item_list`), bóc tách Doanh thu (`money_earned`), RPM, Số dư (`balance`), Lượt xem, và danh sách video vào SQLite `profiles` và `statisticTable`.
  2. **Tầng 2 (DOM Hydration)**: Bóc tách từ `__UNIVERSAL_DATA_FOR_REHYDRATION__` và `SIGI_STATE` khi tải trang công khai kênh qua proxy của profile.
  3. **Tầng 3 (Offline SQLite Cookie Inspection)**: Đọc trực tiếp tệp SQLite `{profile_dir}/Default/Network/Cookies` bằng thuật toán giải mã Windows LDAP FileTime (`(expires_utc / 1000000) - 11644473600`). Nhận diện `sessionid` để tự động gán `state_loggin_browser = 1` (`LIVE`) hoặc `0` (`DIE`).

## 2. Quy Chuẩn Proxy C++ Trong Nhân Orbita v115+
- **Tuyệt đối không truyền `--proxy-server` kèm mật khẩu trên CLI**: Tránh lộ credential trong Task Manager / WMI và tránh pop-up modal `HTTP 407 Proxy Authentication Required`.
- **Cơ chế C++ Preferences Injection**: Inject cấu hình proxy trực tiếp vào `{profile_dir}/Default/Preferences` dưới khóa `gologin.proxy`:
  ```json
  "proxy": {
    "mode": "fixed_servers",
    "server": "protocol://user:pass@host:port",
    "username": "user",
    "password": "pass",
    "schema": "protocol"
  }
  ```
- **Quy tắc cờ `--user-data-dir`**: Bắt buộc luôn nằm ở vị trí **CUỐI CÙNG** trong danh sách tham số Chromium.
- **Phòng thủ WebRTC & IPv6**: Bắt buộc có cờ `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` và `--disable-ipv6`.

## 3. Cập Nhật Live Trên Giao Diện PyQt6
- Mọi cập nhật dữ liệu từ background worker hoặc sniffer đều phát qua `AppSignalBus.instance().profile_updated.emit(profile_id, data)`.
- `MainWindow._on_profile_updated` tự động gọi `refresh_profiles()` để làm mới 28 cột MMO trên bảng `ProfileTableWidget` tức thì.
