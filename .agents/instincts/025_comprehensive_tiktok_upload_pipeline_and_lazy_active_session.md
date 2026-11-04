# Instinct 025: Comprehensive TikTok Upload Pipeline, LazyActiveSession & Process Scan Throttling

## Bối Cảnh (Context)
Trong chu trình thực hiện kiểm thử thực tế toàn diện tính năng Upload Video lên TikTok cho hệ thống TikTok Manager 2026:
- Quá trình tải lên sử dụng cơ chế Tri-Modal Transport SDK (SamMonny): VOD/TOS chunked streaming (5MB) kết hợp In-Page V8 fetch injection và tự động fallback sang Headless Studio DOM automation.
- CSDL SQLite lưu trữ profile với khóa chính số nguyên `id` (e.g. `25`), trong khi daemon GoLogin và thư mục profile trên đĩa đặt tên theo `uuid` (`604ba293-b3b8-427c-89f4-d1f5c20649c6`).
- Khi gọi `session = session_factory(...)`, `AntidetectSession` chưa được kích hoạt (`.start()`), dẫn đến lỗi `Session is not active. Call .start() or use 'with' context manager.` khi truy cập `.cdp`.
- Việc kiểm tra trạng thái profile chạy thông qua `psutil.process_iter(["name", "cmdline"])` trên Windows gây nghẽn UI nếu gọi liên tục mỗi 1.5s cho nhiều profile.

## Giải Pháp Kỹ Thuật Chuẩn (Standard Engineering Solution)

### 1. Kiến Trúc LazyActiveSession & Tự Động Thu Hồi Tài Nguyên
- Bọc `AntidetectSession` trong `LazyActiveSession`: Trì hoãn việc khởi động trình duyệt cho đến khi thực sự có truy cập vào thuộc tính `cdp`, `actions`, `navigate`, hoặc `goto`.
- Trong `SamMonnyTikTokAdapter.upload_video`, sử dụng `tracking_session_factory` để lưu tham chiếu phiên hiện tại và luôn đảm bảo gọi `active_session.close()` cùng `MemoryManager.trim_working_set()` trong khối `finally:`.
- Giúp tiết kiệm 100% RAM/CPU nếu tác vụ sử dụng Direct Post API, đồng thời đảm bảo không bao giờ để lại tiến trình trình duyệt mồ côi (zombie browser) sau khi tải lên hoàn tất.

### 2. Phân Giải Định Danh Tự Động (Integer ID to UUID)
- Trong `_default_session_factory`, kiểm tra nếu `profile_id` là số nguyên hoặc chuỗi số, tự động truy vấn `ProfileRepository.get_by_id()` để lấy trường `uuid` thực tế từ CSDL SQLite trước khi truyền vào `AntidetectEngine.session(...)`.

### 3. Thuật Toán Cắt Gọt Tiêu Đề Bảo Toàn Hashtag (Budget Clamping)
- Trong `clamp_caption`, khi cắt ngắn phần thân văn bản (`body_text`), luôn trừ đi chiều dài của dấu `...` (3 ký tự) từ `allowed_body_len` để tổng độ dài văn bản không vượt quá ngân sách cho phép, tránh làm mất cụm `#hashtag` ở cuối chuỗi.

### 4. Bộ Đệm Quét Tiến Trình Hệ Điều Hành (OS Process Scan Cache)
- Thêm bộ đệm thời gian 2.5 giây cho `OrbitaLauncher._scan_psutil_for_profile`: Tất cả các kiểm tra profile trong cùng một chu kỳ polling sẽ dùng chung một lần quét danh sách tiến trình Chrome/Orbita, giảm thời gian thực thi từ hàng giây xuống còn micro-giây và loại bỏ hoàn toàn hiện tượng nghẽn UI thread.

## Quy Chuẩn Bắt Buộc (Mandatory Rules)
- Luôn kiểm tra quyền riêng tư (Privacy) an toàn (ưu tiên `SELF_ONLY` khi chạy test) để tránh gửi spam ra công chúng trong lúc kiểm thử.
- Mọi video tải lên thành công đều phải được di chuyển vật lý vào thư mục con `_posted/` và cập nhật đường dẫn mới vào CSDL `video_registry`.
