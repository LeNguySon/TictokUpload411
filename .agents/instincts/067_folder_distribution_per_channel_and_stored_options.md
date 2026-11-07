# 067 — Nạp thư mục phân bổ video: giãn cách theo kênh, kiểm tra file, lưu tuỳ chọn

Đã kiểm chứng trên bản sao CSDL thật ngày 2026-11-07.

## Lỗi đã gặp
- **Giãn cách tính theo thứ tự toàn lô:** dùng `idx * interval`. Với 3 kênh × 12 giờ, mỗi kênh thực tế 36 giờ mới đăng một lần, và video cuối bị đẩy tới +4 ngày.
- **Không tính video kênh đã có sẵn trong hàng đợi:** video mới chỉ cách video sẵn có 2 giờ, dù yêu cầu 12 giờ.
- **Không kiểm tra file:** `.mp4` 0 byte và `.avi` vẫn được nạp, đến lúc đăng mới lỗi.
- **Tuỳ chọn trong dialog không được lưu:** bình luận/duet/stitch/HD/nhãn AI không có cột trong `video_registry`.
  - Video người dùng đánh dấu "AI tạo" vẫn bị đăng KHÔNG có nhãn AI. TikTok bắt buộc nhãn này, nên dễ bị gậy vi phạm.

## Quy tắc
- Ô "Khoảng cách" (mặc định 12 giờ, chỉnh được 1–72 giờ) là khoảng cách giữa 2 video **của cùng 1 kênh**. Các kênh đăng song song.
  - Lượt xếp đầu tiên của mỗi kênh = `max(now + 5 phút, latest_pending_schedule(kênh) + interval)`.
- Mọi đường nạp video đều phải qua `validation_policy.validate_file`. Bộ đếm "N video" trong dialog dùng đúng quy tắc đó.
- Tuỳ chọn upload được lưu cùng video (`register_or_update(upload_options=...)`).
  - `execute_upload`: tham số truyền vào được ưu tiên, sau đó tới cột đã lưu, cuối cùng là mặc định của TikTok.
- Hai hàm `distribute_*` dùng chung một luồng (`_scan_video_files` → `_collect_available_videos` → `_assign_and_register`). Đừng nhân bản logic nữa.
- Fixture video trong test phải ≥ 1 KB (mức tối thiểu của chính sách kiểm tra).
- Đừng dùng `sed` với `\x00`: nó ghi byte NUL thật vào file. Dùng một script Python.
