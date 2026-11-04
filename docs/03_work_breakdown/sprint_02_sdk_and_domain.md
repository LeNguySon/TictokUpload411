# Sprint 2: SDK Adapter & Domain Engine Core

- **Thời lượng dự kiến:** Tuần 2
- **Mục tiêu chính:** Xây dựng adapter chính thức kết nối SamMonny SDK 1.8.1, triển khai các dịch vụ nghiệp vụ cốt lõi: Quản lý hồ sơ, Đồng bộ chỉ số kênh và Quản lý hàng đợi video.

---

### `TSK-06-SDK-ADAPT`: Triển Khai SamMonny TikTok Adapter (Official Mode Only)
- **Loại hình:** Tích hợp SDK / Infrastructure
- **Tiền đề:** `TSK-03-REPO`, `TSK-04-VAULT`
- **Mô tả công việc:**
  1. Tạo lớp `TikTokOfficialAdapter` kết nối trực tiếp với `sammonny.platforms.tiktok`:
     - Sử dụng `TikTokPublisherAdapter` và `TikTokDirectPostClient`.
     - Tuyệt đối không import hoặc gọi luồng cookie/headless.
  2. Xây dựng lớp giả lập `FakeTikTokAdapter` phục vụ kiểm thử đơn vị độc lập mà không cần kết nối mạng hoặc token thật.
  3. Xây dựng các hàm:
     - `validate_capability(profile_id)`
     - `fetch_creator_stats(profile_id)`
     - `upload_video_chunked(profile_id, video_path, caption, privacy, progress_cb, cancel_check)`
     - `reconcile_publish_status(profile_id, publish_id)`
- **Đầu ra bàn giao:**
  - `infrastructure/tiktok/sammonny_adapter.py`
  - `tests/mocks/fake_sammonny_sdk.py`
  - Unit test `tests/unit/test_sammonny_adapter.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Gọi thử nghiệm thành công toàn bộ chu trình upload phân đoạn qua `FakeTikTokAdapter`.
  - [ ] Xử lý đúng ngoại lệ `TokenExpired` -> chuyển thành `AuthorizationRequiredException`.

---

### `TSK-07-ACC-SVC`: Triển Khai Account Management Domain Service
- **Loại hình:** Nghiệp vụ / Application Service
- **Tiền đề:** `TSK-03-REPO`, `TSK-04-VAULT`
- **Mô tả công việc:**
  1. Xây dựng `AccountService` điều phối các hoạt động của thực thể Profile:
     - `create_profile(name, project_id, proxy_id, notes)`
     - `batch_import_profiles(records: list[dict])`: Hỗ trợ đọc từ clipboard / tệp CSV, chuẩn hóa dữ liệu, loại bỏ trùng lặp UUID.
     - `update_profile_proxy(profile_id, proxy_id)`
     - `soft_delete_profile(profile_id)` và `restore_profile(profile_id)`
  2. Định nghĩa các quy tắc kiểm tra tính hợp lệ (Validation Rules): tên không được rỗng, proxy hợp lệ.
- **Đầu ra bàn giao:**
  - `application/services/account_service.py`
  - `domain/models/profile.py`
  - Unit test `tests/unit/test_account_service.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Import thử danh sách 50 profile mẫu, thời gian xử lý < 200ms.
  - [ ] Thao tác xóa hồ sơ chuyển `is_trashed = 1`, không xóa vật lý khỏi CSDL.

---

### `TSK-08-ANALYTICS-SVC`: Triển Khai Analytics & Provenance Service
- **Loại hình:** Nghiệp vụ / Application Service
- **Tiền đề:** `TSK-03-REPO`, `TSK-06-SDK-ADAPT`
- **Mô tả công việc:**
  1. Xây dựng `AnalyticsService` điều phối việc thu thập chỉ số tài khoản:
     - Kiểm tra trạng thái ủy quyền và quyền hạn của profile.
     - Gọi `TikTokOfficialAdapter.fetch_creator_stats()`.
     - Chuẩn hóa số liệu trả về: Views 30 ngày (`views_month`), Followers, Likes, Tổng số Video.
  2. Ghi nhận dữ liệu nguồn gốc (Data Provenance): Lưu vào `tiktok_report_observations` với `source = 'official_sdk'` và thời điểm quan sát.
  3. Cập nhật các trường tổng hợp trong bảng `profiles` và bảng chi tiết `statisticTable` trong cùng 1 transaction.
- **Đầu ra bàn giao:**
  - `application/services/analytics_service.py`
  - `domain/models/metric_snapshot.py`
  - Unit test `tests/unit/test_analytics_service.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Phân biệt tuyệt đối giữa lượt xem 30 ngày (`views_month`) và tổng lượt xem trọn đời (`total_views`).
  - [ ] Xử lý an toàn khi API trả về thiếu trường hoặc dữ liệu rỗng.

---

### `TSK-09-UPLOAD-SVC`: Triển Khai Upload Queue Service & Reconcile Engine
- **Loại hình:** Nghiệp vụ / Application Service
- **Tiền đề:** `TSK-03-REPO`, `TSK-06-SDK-ADAPT`
- **Mô tả công việc:**
  1. Xây dựng `UploadQueueService`:
     - Kiểm tra file video tồn tại, đọc thời lượng, dung lượng, tính mã băm SHA256.
     - Đối chiếu bảng `video_registry`: Nếu video đã được xuất bản (`status = 'published'`), cảnh báo người dùng.
     - Tạo bản ghi mới trong `tiktok_queue` với trạng thái `pending`.
  2. Xây dựng logic Reconcile: Khi tiến trình upload bị ngắt kết nối không rõ nguyên nhân, gọi hàm kiểm tra đối soát với TikTok để xác nhận trạng thái cuối cùng, tránh tải lên lại gây trùng lặp nội dung.
- **Đầu ra bàn giao:**
  - `application/services/upload_service.py`
  - `domain/policies/upload_policy.py`
  - `domain/policies/validation_policy.py`
  - Unit test `tests/unit/test_upload_service.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Tính mã băm SHA256 của file video 100MB < 500ms.
  - [ ] Ngăn chặn thành công việc thêm một video đã được đăng tải vào hàng đợi của kênh khác nếu bật cờ chống trùng.

