# 002_domain_concurrency_presentation_instincts.md
## Kinh Nghiệm Thực Chiến Sprints 2, 3 & 4: Hạt Nhân Domain, Đa Luồng Qt & Giao Diện Bảng Kép Fluent UI

Tài liệu này ghi nhận các bài học kỹ thuật quan trọng trong quá trình triển khai Sprints 2, 3, 4 theo chuẩn công nghiệp ECC (affaan-m/ecc).

---

### 1. SamMonny Tri-Modal SDK Integration
- **Root Package Exports**: Các lớp `TikTokPublisherAdapter`, `TikTokDirectPostClient`, `UploadMode`, `UploadResult`, `ProxyHealthResult`, `RemoteStatus` được export trực tiếp từ root namespace `sammonny` (`from sammonny import ...`). Không nên import từ các subpath nội bộ như `sammonny.core.models` hay `sammonny.platforms.tiktok.uploader` vì cấu trúc nội bộ có thể tái phân phối.
- **Smart Proxy Parsing**: Định dạng proxy MMO thứ 5 (`host:port:user:pass:https://rotate.link`) có chứa token URL có dấu hai chấm. Cần bóc tách URL trước khi phân tách host/port/user/pass để tránh làm gãy bộ tách chuỗi.

---

### 2. SQLite Repositories & UUID Auto-Generation
- Bảng `profiles` yêu cầu cột `uuid NOT NULL`. Khi tạo mới profile bằng dictionary trong `ProfileRepository.create(data)`, luôn tự động sinh `data["uuid"] = str(uuid.uuid4())` nếu người gọi không truyền vào.
- Tránh định nghĩa hai hàm trùng tên trong cùng một class Python (ví dụ: `def update(self, profile_id, **fields)` và `def update(self, profile_id, data)`). Thay vào đó, gom vào một hàm duy nhất hỗ trợ cả `data: dict | None = None` và `**fields: Any`.

---

### 3. Qt Concurrency & Memory Hygiene (QThreadPool)
- Bắt buộc dùng `QRunnable` kết hợp `QObject` signal bridge để chạy các tác vụ nặng (Upload SDK, check proxy hàng loạt, đồng bộ chỉ số MMO). Tuyệt đối không gọi I/O trực tiếp trên Main Thread.
- Trong `BaseWorker.run()`, luôn gọi `sammonny.MemoryManager.trim_working_set()` trong khối `finally` để giải phóng bộ nhớ RAM dư thừa của Windows và Chromium sau mỗi lượt chạy.

---

### 4. Windows 11 Fluent UI Dual-Table Synchronization
- Sử dụng `QSplitter(Qt.Orientation.Vertical)` để phân tách Bảng Profiles (28 cột MMO) và Bảng Video Queue (14 cột).
- Sử dụng `ProgressBar` từ `qfluentwidgets` lồng vào cột "Source" của bảng video và kết nối với tín hiệu `upload_progress(video_id, done, total, pct)` để cập nhật mượt mà theo thời gian thực mà không làm giật khung hình.

