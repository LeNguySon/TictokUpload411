# Instinct 004: SamMonny GoLogin SDK Daemon & Real Orbita Engine Integration

## Background & Architecture
Hệ thống TikTok Account & Video Manager (`TAVM-2026-WIN`) kết nối với lõi GoLogin Antidetect thông qua bộ SDK C++/Rust `SamMonnygocLiengXiPoker`.

## Key Technical Lessons Learned

1. **Dual-Port Daemon Architecture (Ports 7654 & 36912)**:
   * `sammonny-daemon.exe` điều khiển song song 2 cổng:
     * Port `7654`: Native REST API nội bộ (`/health`, `/api/v1/profiles`).
     * Port `36912`: GoLogin SDK Drop-in Compatibility Server (`/service/check-server`, `/service/start-profile`).
   * Để đảm bảo SDK hoạt động không bị lỗi rớt kết nối, ứng dụng phải có `SamMonnyDaemonSupervisor` kiểm tra `check_health()` và tự động khởi động ngầm tiến trình `sammonny-daemon.exe serve --port 7654 --sdk-port 36912` với cờ `CREATE_NO_WINDOW`.

2. **Real Orbita Binary Discovery**:
   * Nhân trình duyệt Orbita thực tế được cài đặt tại:
     * `C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-152\chrome.exe` (Chromium 152)
     * `C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-139\chrome.exe`
     * `C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-123\chrome.exe`
   * `OrbitaLauncher` phải ưu tiên dò tìm các đường dẫn thực tế này trước khi fallback về các vị trí mặc định.

3. **Bayesian Antidetect Fingerprint Generation**:
   * Khi tạo profile mới, không chèn bản ghi SQLite tĩnh thủ công. Hãy ủy quyền cho `GoLogin.create({"name": name, "os": "win", "proxy": proxy})`.
   * SDK sẽ sinh ngẫu nhiên nhưng có tương quan vi sai sinh trắc học (Bayesian Correlation) giữa User-Agent, Canvas Noise, WebGL Vendor/Renderer (ANGLE Direct3D11), Audio Noise, Hardware Concurrency, và gán UUID hợp chuẩn.

4. **Bi-Directional Profile Syncing**:
   * Cơ sở dữ liệu `gologin.db` tại `D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\gologin.db` lưu trữ các profile thực tế.
   * `GoLoginSyncService` cho phép đồng bộ toàn bộ profile thực tế kèm theo cấu hình fingerprint đầy đủ vào bảng `profiles` của ứng dụng qua cơ chế upsert an toàn.
