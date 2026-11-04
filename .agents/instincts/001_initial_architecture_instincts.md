# Bản Năng Kỹ Thuật Ban Đầu (Initial Baseline Instincts)
## Mã Nhận Diện: `INSTINCT-001`

1. **Giao Diện Dual-Table Windows 11**:
   - Bảng 1 (Accounts Table) chứa đủ 28 cột MMO từ ảnh thực tế, có hỗ trợ Preset Chips (*Tổng quan*, *Doanh thu*, *Kỹ thuật*).
   - Bảng 2 (Videos Table) có thanh đếm `Đã chọn X / Y video`, nút Lên lịch, ô tìm kiếm debounce và ProgressBar bo góc Fluent.
   - Luôn sử dụng `QSplitter` phong cách Fluent chia đôi hai bảng, ngăn cách bằng thanh trượt có thể kéo tùy biến.

2. **Cơ Sở Dữ Liệu SQLite WAL & DPAPI Triggers**:
   - SQLite bắt buộc phải có `PRAGMA journal_mode = WAL;`, `foreign_keys = ON;`, `busy_timeout = 10000;`, `cache_size = -64000;`.
   - Mọi thao tác ghi secret vào `profiles` hay `tiktok_sessions` đều qua trigger `gloglin_protect` (Windows DPAPI).

3. **Tích Hợp SamMonny SDK**:
   - Luôn kết nối qua `TikTokPublisherAdapter` hỗ trợ 3 chế độ: `OFFICIAL_DIRECT_POST`, `COOKIE_API_HYBRID`, `HEADLESS_STUDIO`.
   - Tận dụng `session.http` (In-Kernel Egress) để tránh lộ JA3/JA4 TLS Fingerprint của Python requests.
   - Luôn gọi `MemoryManager.trim_working_set()` sau khi tắt tab hoặc xong upload để giải phóng 99% RAM của Chromium.

