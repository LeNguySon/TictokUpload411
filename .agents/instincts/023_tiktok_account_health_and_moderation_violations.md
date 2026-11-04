# Bản Năng Kỹ Thuật 023: Thu Thập & Hiển Thị Chi Tiết Sức Khỏe Kênh TikTok, Gậy Vi Phạm & Gậy Nguyên Tác

## 1. Bối Cảnh & Cơ Chế Kỹ Thuật Của TikTok Creator Center
- Trong MMO TikTok, việc phát hiện sớm gậy vi phạm chính sách và gậy nguyên tác là yếu tố sinh tử:
  1. **Gậy Nguyên Tác (Unoriginality Strike / Ineligible for FYP)**: TikTok gắn cờ video bị biên tập lại (reup) không tạo thêm giá trị sáng tạo mới, dẫn đến việc bị loại khỏi nguồn cấp dữ liệu Dành cho bạn (FYP) và bị tước quyền kiếm tiền Creator Rewards.
  2. **Gậy Tiêu Chuẩn Cộng Đồng (Community Guidelines Violation)**: Vi phạm chính sách bản quyền, nội dung nhạy cảm, tích lũy $1/3, 2/3, 3/3$ gậy trước khi bị đình chỉ kênh vĩnh viễn.
  3. **Bản Quyền Âm Thanh (Sound Muted)**: Video bị tắt âm thanh do vi phạm quyền tác giả thương mại.

## 2. Các Endpoint Cốt Lõi Để Thu Thập
1. **Endpoint Sức Khỏe Kênh & Gậy Tích Lũy**:
   - `GET https://www.tiktok.com/api/creator/account/standing/?aid=1988`
   - Bóc tách: `standing_level` (`Good`, `Warning`, `High Risk`, `Suspended`), `active_strikes` (0/3, 1/3, 2/3, 3/3), `restricted_features`.
   - Cập nhật vào DB: `UPDATE profiles SET account_standing=?, strike_count=?, ttl_violations=? WHERE id=?`.
2. **Endpoint Danh Sách Video Ăn Gậy & Gậy Nguyên Tác**:
   - `GET https://www.tiktok.com/api/creator/violation/list/?aid=1988&count=20`
   - Bóc tách `violation_list`: `item_id`, `title`, `violation_title`, `violation_reason`, `appeal_deadline`, `status`.
   - Lưu trữ và cập nhật vào bảng `violateVideos` với `ON CONFLICT(profile_id, video_id) DO UPDATE`.

## 3. Kiến Trúc Giao Diện & Tích Hợp
- **`AccountHealthDialog`**:
  - 4 Thẻ KPI: Chất lượng tài khoản, Gậy vi phạm tích lũy, Điểm phạt toàn kênh, Ước tính rủi ro Shadowban.
  - Diagnostic Box: Chẩn đoán thuật toán & Cảnh báo phân phối.
  - Bảng Tab 1: Danh sách video bị gậy vi phạm & gậy nguyên tác (kèm hạn chót kháng cáo).
  - Bảng Tab 2: Lịch sử vé kháng cáo.
  - Nút Quét Sức Khỏe Kênh chạy nền trên thread pool bất đồng bộ, cập nhật UI và InfoBar.
- **Bảng `ProfileTableWidget`**:
  - Cột 16 (`CS`): Hiển thị `🔴 1/3 Gậy`, `🟢 Tốt`, `🟡 Cảnh báo`, `💎 Đủ Quỹ`.
  - Cột 26 (`VVP`): Hiển thị số lượng video dính gậy từ bảng `violateVideos`.
  - Menu chuột phải: `"🛡️ Sức Khỏe Kênh & Gậy Vi Phạm..."` mở `AccountHealthDialog`.
  - Settings Menu: Action `"Kiểm Tra Sức Khỏe Kênh & Gậy Vi Phạm..."`.

## 4. Quy Chuẩn Cho Các Agent Sau
- Khi kiểm tra kênh, luôn ưu tiên đọc cookie hợp lệ từ trường `cookies_json` hoặc `cookies_browser` của hồ sơ.
- Mọi truy vấn mạng TikTok bắt buộc dùng `curl_cffi` với `impersonate="chrome120"` để giữ tính nhất quán vân tay TLS.
- Không bao giờ block Main GUI Thread khi quét vi phạm hàng loạt.

