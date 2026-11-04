# Bản Năng Kỹ Thuật: Tự Động Cách Ly Video (_posted/) & Chống Đăng Trùng Lặp

## 1. Cơ Chế Cách Ly Vật Lý (Physical File Isolation)
- Khi một video được upload thành công lên TikTok (`UploadWorker` -> `upload_completed`), không chỉ đánh dấu trạng thái trong cơ sở dữ liệu mà còn phải di chuyển vật lý file video gốc sang thư mục `_posted/` cùng cấp.
- Giải pháp này ngăn chặn triệt để tình trạng:
  1. Người dùng quét lại thư mục chứa video và vô tình đăng trùng một video nhiều lần.
  2. Các kênh vệ tinh bị TikTok quét bản quyền hoặc đánh spam do đăng trùng file vật lý chưa qua xử lý.

## 2. Quy Tắc Triển Khai An Toàn
- **Idempotency**: Kiểm tra nếu file đã nằm trong `_posted/` thì không thực hiện di chuyển lại.
- **Xử lý xung đột tên (Collision Avoidance)**: Nếu trong thư mục `_posted/` đã tồn tại file cùng tên, tự động đánh số tăng dần `{stem}_{counter}{suffix}` (ví dụ: `clip_1.mp4`, `clip_2.mp4`...).
- **Đồng bộ CSDL**: Sau khi di chuyển file, gọi `VideoRepository.update_metadata(video_id, file_path=..., file_name=...)` để cập nhật vị trí mới vào bảng `video_registry`.
- **Bộ lọc kéo thả thư mục (Folder Drop)**: Trong `VideoQueueTableWidget.dropEvent`, khi quét đệ quy các thư mục được kéo vào bảng, bắt buộc bỏ qua mọi file có thư mục cha là `_posted` hoặc `.posted`.
