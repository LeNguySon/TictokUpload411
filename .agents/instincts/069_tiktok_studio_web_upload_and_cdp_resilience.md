# Instinct 069: TikTok Studio Web Upload & CDP Resilience (2026 Modernization)

## Context & Problem
Khi thực hiện tải video lên kênh TikTok thực qua Cookie / Web Studio Automation (Profile 78 `@swall.pain`), xuất hiện các vấn đề kỹ thuật sâu:
1. **Hàng đợi video cũ bị lỗi kẹt**: 124 video từ đợt import cũ gán cho profile 17 (`aaaa`) với `status = 'failed'` và `error_message = NULL`, hiển thị cột Nhật ký là `-` và bảng thông báo "Hàng đợi trống" khi bấm Upload vì chỉ quét `available`.
2. **TikTok Studio URL chuyển hướng 2026**: Endpoint cũ `/creator-center/upload` bị TikTok đổi hướng sang `/tiktokstudio/upload`.
3. **Joyride Modal cản trở DOM**: TikTok Studio phiên bản mới luôn kích hoạt tooltip Joyride Onboarding ("スマートフォンで動画をプレビューする...") với nút "OK", che khuất và chặn tương tác với nút Post.
4. **Đa ngôn ngữ Profile (Tiếng Nhật/Việt/Anh)**: Profile 78 sử dụng giao diện Tiếng Nhật. Nút Post là `投稿`, chế độ riêng tư là `誰でも` (Công khai) / `自分のみ` (Chỉ mình tôi). Code cũ chỉ tìm `post` / `đăng` dẫn đến timeout 600s.
5. **Headless Chromium CDP Compositor Deadlock**: Lệnh `Input.dispatchMouseEvent` bị treo timeout 30.0s do Chromium Headless không gửi phản hồi compositor khi chuột di chuyển offscreen.
6. **V8 Context Invalidation (-32000)**: Khi SPA Semi Design re-render, V8 default execution context bị phá hủy, gây lỗi `-32000: Cannot find default execution context`. Đồng thời typo `grantUniveralAccess` (thiếu chữ 's') làm hỏng việc tạo Isolated World.
7. **Ẩn video đã xuất bản trong hàng đợi**: `video_repository.list_available(only_available=False)` trước đây loại trừ `status = 'published'`, khiến video vừa đăng xong bị biến mất khỏi bảng và không hiển thị trạng thái hoàn thành.

---

## Technical Solution & Implementation

### 1. Nâng cấp UI & Quản lý Hàng Đợi (VideoQueueTableWidget)
- Bổ sung 2 tín hiệu và menu chuột phải:
  - `"Đặt lại Sẵn sàng / Thử lại"` (`reset_status_requested`) -> Đưa các video được chọn về `available`, xóa lỗi.
  - `"Gán Tài Khoản Đang Chọn Cho Video"` (`assign_profile_requested`) -> Gán profile đang chọn cho các video được bôi đen.
- Cột Nhật Ký Upload: Thay thế dấu gạch ngang trơ trọi bằng `"❌ Thất bại (Chưa thử lại)"`, `"Sẵn sàng đăng"`, hoặc `"✅ Đã xuất bản"`.
- Bổ sung `published` vào `list_available(only_available=False)` để người dùng theo dõi được video đã đăng thành công ngay trên bảng.

### 2. Chuẩn hóa Endpoint & Polling File Input
- Cập nhật hằng số `STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"`.
- Polling tìm `<input type="file">` tối đa 15 giây để chờ React SPA Semi Design mount hoàn tất DOM trước khi đính kèm tệp qua `DOM.setFileInputFiles`.

### 3. Vượt Chướng Ngại Joyride & Đa Ngôn Ngữ Nút Bấm
- Tự động tìm và bấm nút `"OK"`, `"了解"`, `"Đồng ý"`, `"Skip"` của Joyride modal trước khi tương tác.
- Bổ sung bộ lọc đa ngôn ngữ:
  - Nút đăng: `['post', 'đăng', 'schedule', 'lên lịch', '投稿']`.
  - Quyền riêng tư: `['public', 'everyone', 'công khai', '誰でも', '公開']` và `['self', 'private', 'chỉ mình tôi', '自分のみ', '非公開']`.

### 4. Khắc Phục Treo Chuột & V8 Execution Context Resilience
- Loại bỏ lệnh treo `Input.dispatchMouseEvent` trên headless, thay thế bằng dispatch trực tiếp qua DOM: `btn.scrollIntoView({ behavior: 'instant', block: 'center' }); btn.click();` đảm bảo kích hoạt 100% trong 0.1 giây.
- Sửa lỗi chính tả `grantUniversalAccess: True` trong `Page.createIsolatedWorld`.
- Khi `Runtime.evaluate` gặp bất kỳ lỗi `CdpError` (-32000 context destroyed), tự động fallback sang `evaluate_isolated()` với Isolated World V8 tàng hình, không bao giờ block luồng.

---

## Verification & Metrics
- Đăng tải thành công thực tế Video #4 (`Ăn cá mà không muốn nhả xương thì ăn cá gì？-(256p15).mp4`) lên Profile #78 (`@swall.pain`).
- Thời gian xuất bản: **14.68 giây** (`RemoteStatus.PUBLISH_COMPLETE`, ID: `studio_1794034814`).
- Toàn bộ 57/57 unit tests liên quan đạt 100% PASS; `ruff check` sạch không lỗi.
- Hình ảnh bằng chứng lưu tại:
  - `post_confirmation_proof.png`: Hộp thoại xác nhận xuất bản từ TikTok Studio DOM.
  - `live_upload_cookie_api_proof.png`: Giao diện ứng dụng máy tính hiển thị trạng thái đã xuất bản thành công.

