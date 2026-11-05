# Instinct 027 — Multi-Threaded Upload Progress Segregation & AgentShield Log Viewer
## Ngày ghi nhận: 2026-11-05

## Bối cảnh kỹ thuật
- Khi triển khai upload đa luồng đồng thời nhiều video (`UploadWorker` chạy song song trên `QThreadPool`), các dòng log và sự kiện tiến trình nếu xuất ra chung một stream hoặc một luồng console sẽ bị đan xen (interleaved). Người dùng không thể phân biệt được video nào đang băm hash, video nào đang truyền chunk dữ liệu, hay video nào gặp lỗi mạng.

## Nguyên nhân gốc rễ & Thách thức
1. **Trộn lẫn dữ liệu đa luồng (Cross-Thread Log Interleaving)**: Nhiều luồng cùng gọi `logger.info` mà không có cơ chế gắn khóa `video_id` và tách bộ nhớ đệm (buffer) theo từng video.
2. **Nguy cơ rò rỉ thông tin nhạy cảm (AgentShield Compliance)**: Các bản tin trao đổi HTTP giữa SDK và máy chủ TikTok thường chứa `sessionid`, cookie xác thực hoặc `access_token`. Nếu đổ trực tiếp vào `QTextBrowser` sẽ vi phạm tiêu chuẩn an ninh AgentShield.
3. **Hiệu năng giao diện (UI Responsiveness)**: Nếu cập nhật log dạng text browser liên tục với số lượng dòng lớn mà không giới hạn bộ nhớ (ring buffer) sẽ gây tràn RAM và giật lag giao diện người dùng.

## Giải pháp kiến trúc chuẩn
1. **Kiến trúc Tín Hiệu Định Danh (Tagged Qt Signal Architecture)**:
   - Thêm `upload_log = pyqtSignal(int, str, str, str, str)`: `(video_id, timestamp, stage, message, level)`
   - Thêm `upload_stage_changed = pyqtSignal(int, str)`: `(video_id, stage_text)`
   - `UploadWorker` và `UploadService` phát log qua hàm callback an toàn có gắn `video_id`.
2. **Bộ Nhớ Đệm Vòng Lặp & Bộ Lọc Video (`VideoUploadLogWidget`)**:
   - Sử dụng `deque(maxlen=500)` cho từng `video_id` và `deque(maxlen=2000)` cho luồng tổng hợp, ngăn chặn rò rỉ bộ nhớ.
   - Hỗ trợ dropdown chọn xem tổng hợp `[Tất cả video]` hoặc lọc riêng từng video đang chạy / đã xong.
   - Menu chuột phải trên bảng video `"Xem Nhật Ký Upload (Logs)..."` kích hoạt slot `focus_video(video_id)`.
3. **Cơ chế Masking Tự Động AgentShield**:
   - Hàm `redact_sensitive_text(text)` tự động phát hiện và che giấu toàn bộ chuỗi token (`act.*`, `sessionid`, `bearer`, `access_token`, `cookie: ...`) thành `[REDACTED]`.
4. **Cập nhật Bảng Tiến Trình Cục Bộ (Targeted Row Update)**:
   - Cột `Tình trạng` (Col 9) và `Source/ProgressBar` (Col 10) cập nhật đúng hàng theo `find_row_by_video_id`, không gọi reload lại toàn bộ dữ liệu bảng khi worker đang chạy.

