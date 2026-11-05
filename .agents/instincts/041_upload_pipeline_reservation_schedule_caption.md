# Instinct 041: Upload Pipeline — Claim Lifecycle, Native Scheduling, Caption & Isolation

Kiểm toán offline luồng upload (không upload thật). Test: `tests/unit/test_upload_pipeline_audit.py`.

## 1. Vòng đời trạng thái video
`available` → (scheduler: `try_reserve` → `reserved`) → `claim_for_upload` → `uploading` → `published` | `failed` | (mơ hồ) giữ `uploading`.
- `UploadService.execute_upload` **không** gọi `try_reserve` nữa: dùng `VideoRepository.claim_for_upload(video_id, profile_id)` — nhận `available`, `failed` (thử lại thủ công) hoặc `reserved` **cho đúng profile đó**. Trước đây scheduler reserve rồi worker reserve lần 2 ⇒ mọi video hẹn giờ tự động đều thất bại và kẹt `reserved` vĩnh viễn.
- Kiểm tra profile tồn tại **trước** khi ghi DB (id sai còn vi phạm khóa ngoại `assigned_profile_id`).
- Sau khi claim, mọi lỗi (profile DIE/CHECKPOINT, mất bản ghi video, exception adapter) ⇒ `mark_error` ⇒ `failed`. Không bao giờ để kẹt `reserved`.
- `result.success` mà không có `publish_id` vẫn là **published** (cookie hybrid / hẹn giờ có thể không trả id). Ghi `failed` sẽ mời người dùng đăng lại ⇒ trùng video.
- `result.is_ambiguous` (đã gửi nhưng chưa xác nhận) ⇒ giữ `uploading`, không tự thử lại; cần đối soát trên TikTok.
- `list_available(only_available=False)` (bảng hàng đợi) hiển thị cả `failed` để có thể thử lại; scheduler và "Bắt đầu đăng" chỉ lấy `available` (không tự lặp video lỗi).
- `video_registry.error_message` (migration `ADD COLUMN` trong `runner.py`): `mark_error` lưu lý do đã **che dữ liệu nhạy cảm** bằng `RedactionFilter.redact` và cắt còn `MAX_ERROR_MESSAGE_CHARS` (1000); `claim_for_upload` và `mark_published` xóa về NULL. Bảng hàng đợi đọc sẵn cột này (cột 11). Test: `tests/unit/test_video_error_message_column.py`.

## 2. Hẹn giờ gốc của TikTok
- SDK gửi mọi `schedule_time` với `post_type=1`. TikTok chỉ nhận lịch **15 phút .. 10 ngày** tới. `tiktok_schedule_or_none()` (upload_policy) chỉ chuyển thời gian hợp lệ; thời gian đã tới hạn (scheduler của app dispatch đúng giờ) hoặc quá xa ⇒ đăng ngay.
- Test có thời gian hẹn phải dùng thời điểm **tương đối** (`now + 2h`), không viết cứng ngày.

## 3. Caption
- Cột `video_registry.file_name` **là caption** (caption spin từ template được lưu ở đây). Không ghi đè nó bằng tên file: `isolate_video_file` chỉ cập nhật `file_path`.
- Không có template thì caption từng là tên file ("clip.mp4"); `caption_from_file_name()` bỏ đuôi video lúc đăng.

## 4. Cách ly file sau upload
- `UploadService.execute_upload` tự cách ly vào `_posted/` dưới profile lock. `main_window._on_upload_completed` **không** cách ly lần nữa (chỉ đọc hàng đợi cho auto-advance, chạy nền).
