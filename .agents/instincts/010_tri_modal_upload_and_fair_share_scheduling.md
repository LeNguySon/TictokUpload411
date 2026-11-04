# Bản Năng Kỹ Thuật: Tự Động Upload Video TikTok Đa Phương Thức & Phân Bổ Công Bằng

## 1. Kiến Trúc Xuất Bản Đa Phương Thức (Tri-Modal Publishing)
- Kế thừa tối đa từ `sammonny.platforms.tiktok` (TDS-ARCH-001 §6.2):
  1. `OFFICIAL_DIRECT_POST`: Sử dụng khi tài khoản có OAuth token trong Windows DPAPI Vault (Chunked HTTP PUT 10MB, init handshake, creator info query).
  2. `COOKIE_API_HYBRID`: Kỹ thuật 3 pha (VOD init $\rightarrow$ TOS 5MB direct chunk streaming tiết kiệm 95% RAM $\rightarrow$ V8 fetch injection inside Orbita Chromium via CDP để vượt SecSDK acrawler WAF / 403 Forbidden).
  3. `HEADLESS_STUDIO`: Tự động hóa trình duyệt Orbita qua CDP DOM (`input[type="file"]`), chuột sinh học Minimum Jerk và vượt popup.

## 2. Thuật Toán Phân Bổ Công Bằng & An Toàn (Gloglin2609)
- **Fair-Share Round-Robin**: Chia đều số video từ folder cho các kênh TikTok đã chọn `profile_ids[idx % len(profile_ids)]`.
- **Deduplication Filtering**: Quét mã hash SHA-256 đối chiếu `video_registry`, tự động loại trừ video đã nạp/đã đăng và video trùng lặp nội bộ.
- **Giãn Cách An Toàn (Cooldown Scheduling)**: Đảm bảo khoảng cách giữa các video đăng trên cùng 1 kênh tối thiểu 12h (hoặc số giờ người dùng cấu hình) nhằm tránh thuật toán phát hiện spam của TikTok.
- **Khóa An Toàn Đa Luồng (Profile Mutex Lock)**: Hàm `get_profile_upload_lock(profile_id)` đảm bảo mỗi tài khoản chỉ được tải lên bởi đúng 1 worker tại một thời điểm.
- **Cắt Caption An Toàn Giữ Hashtag (`clamp_caption`)**: Đảm bảo tổng độ dài không vượt quá 2200 ký tự của TikTok Studio, ưu tiên giữ nguyên toàn bộ chùm hashtag đuôi bài.

