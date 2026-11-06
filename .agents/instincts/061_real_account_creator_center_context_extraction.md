# Instinct 061: Real Account Creator Center Context Extraction & Modern.js Hydration

## Context
Khi thực hiện trích xuất dữ liệu chuyên sâu cho tài khoản TikTok thực tế (@swall.pain) từ phiên cookie hợp lệ, các endpoint REST truyền thống (`/api/creator/...`) trả về lỗi `"url doesn't match"` do kiến trúc định tuyến mới của TikTok Web.

## Tri Thức Kỹ Thuật & Giải Pháp Công Nghiệp

1. **Kiến Trúc Micro-Frontend của TikTok Studio / Creator Center (2026)**:
   - TikTok Web sử dụng nền tảng Modern.js `@pgc-web/micro-fe`.
   - Các trang chính:
     - `https://www.tiktok.com/tiktokstudio`
     - `https://www.tiktok.com/creator-center/`
     - `https://www.tiktok.com/creator-center/content`
     - `https://www.tiktok.com/creator-center/analytics`
   - Dữ liệu nghiệp vụ không cần gọi riêng lẻ các API backend mà được máy chủ SSR nhúng trực tiếp vào thẻ HTML:
     `<script id="__Creator_Center_Context__">`
   - Nội dung bên trong được mã hóa thực thể HTML (`&quot;`, `&amp;`), cần giải mã bằng `html.unescape()` trước khi `json.loads()`.

2. **Cấu Trúc Khối Dữ Liệu `__Creator_Center_Context__`**:
   - `commonAppContext.user`: Chứa `uniqueId`, `secUid`, `avatarUri`, `storeRegion` (GB, US, JP...).
   - `programStatus`: Chứa trạng thái tham gia Quỹ sáng tạo (Creator Rewards) và Chương trình kiếm tiền:
     `{'0': 1, '1': 0, 'Content': 1, 'Comment': 1}`
   - `firstBatchQueryItems.item_list`: Chứa danh sách video thực tế của tài khoản kèm:
     - `item_id`: Mã định danh video TikTok.
     - `play_count` (views), `like_count` (hearts), `comment_count`, `share_count`.
     - `status`: 102 (đang phân phối bình thường).
     - `in_review`: False (đã vượt qua kiểm duyệt).
     - `visibility`: 1 (Công khai).
   - `uploadUserProfile`: Hồ sơ thông tin quyền tác giả và cấu hình tải lên.

3. **Bảo Mật AgentShield & Quy Chuẩn Đệm Cục Bộ**:
   - Cookie phiên thực tế bắt buộc phải được mã hóa ngay lập tức bằng Windows DPAPI (`protect_text()`) trước khi lưu trữ vào bảng `profiles` (`cookies_json`, `cookies_browser`).
   - Avatar người dùng từ CDN ByteDance được tải về cục bộ tại `data/avatars/{profile_id}.jpg` để `CircularAvatarDelegate` render mượt mà, không giật lag GUI.

