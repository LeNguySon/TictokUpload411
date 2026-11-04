# Sprint 3: Động Cơ Đa Luồng & Bất Đồng Bộ (Concurrency Engine)

- **Thời lượng dự kiến:** Tuần 3
- **Mục tiêu chính:** Xây dựng khung worker thread an toàn (`BaseWorker`), tích hợp cơ chế hủy hợp tác (Cooperative Cancellation), phát triển `TikTokSyncWorker` có khoảng trễ jitter và `VideoUploadWorker` tải lên phân đoạn với Exponential Backoff.

---

### `TSK-10-WORKER-BASE`: Xây Dựng Base QRunnable & Trục Tín Hiệu Định Kiểu
- **Loại hình:** Đa luồng / Application Core
- **Tiền đề:** `TSK-01-ENV`, `TSK-05-SEC-LOG`
- **Mô tả công việc:**
  1. Xây dựng lớp trừu tượng `BaseWorker(QRunnable)`:
     - Tích hợp cờ hủy hợp tác `_is_interrupted: bool` với các phương thức `request_interruption()` và `is_interruption_requested()`.
     - Bao bọc toàn bộ phương thức `run()` trong khối `try...except Exception` tự động bắt và phát tín hiệu lỗi, chống crash ứng dụng hoàn toàn.
  2. Hiện thực hóa các lớp Dataclass bất biến trong `application/signals/payload_types.py`.
  3. Xây dựng singleton `AppSignalBus` trong `application/signals/app_signals.py`.
- **Đầu ra bàn giao:**
  - `application/workers/base_worker.py`
  - `application/signals/payload_types.py`
  - `application/signals/app_signals.py`
  - Unit test `tests/unit/test_base_worker.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Gọi `worker.request_interruption()` khiến worker thoát vòng lặp an toàn mà không bị crash hay rò rỉ thread.
  - [ ] Mọi exception phát sinh trong worker đều phát ra tín hiệu `sig_upload_failed` hoặc `sig_sync_profile_done(success=False)` với thông điệp đã redact.

---

### `TSK-11-SYNC-WORKER`: Triển Khai TikTokSyncWorker Bounded Concurrency
- **Loại hình:** Đa luồng / Worker
- **Tiền đề:** `TSK-08-ANALYTICS-SVC`, `TSK-10-WORKER-BASE`
- **Mô tả công việc:**
  1. Xây dựng `TikTokSyncWorker` kế thừa `BaseWorker`:
     - Nhận danh sách các `profile_id` cần đồng bộ.
     - Duyệt tuần tự qua từng profile, kiểm tra `is_interruption_requested()`.
     - Thêm khoảng trễ ngẫu nhiên (Jitter) an toàn từ 1.5 đến 3.0 giây giữa các request để bảo vệ tài khoản.
     - Phát tín hiệu `sig_sync_progress` cập nhật tiến trình từng bước.
     - Khi hoàn tất hoặc lỗi 1 profile, phát `sig_sync_profile_done`.
  2. Khi quét xong toàn bộ danh sách, phát tín hiệu `sig_sync_batch_done` kèm báo cáo tổng kết.
- **Đầu ra bàn giao:**
  - `application/workers/tiktok_sync_worker.py`
  - Unit test `tests/unit/test_tiktok_sync_worker.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Mô phỏng đồng bộ 10 profiles: Tín hiệu tiến độ được phát đều đặn theo thứ tự.
  - [ ] Khi bấm Hủy giữa chừng, worker dừng ngay lập tức tại profile hiện tại, không thực thi các profile còn lại.

---

### `TSK-12-UPLOAD-WORKER`: Triển Khai VideoUploadWorker & Phân Đoạn Chunk
- **Loại hình:** Đa luồng / Worker
- **Tiền đề:** `TSK-09-UPLOAD-SVC`, `TSK-10-WORKER-BASE`
- **Mô tả công việc:**
  1. Xây dựng `VideoUploadWorker` kế thừa `BaseWorker`:
     - Nhận `job_id` của bản ghi trong `tiktok_queue`.
     - Cập nhật trạng thái `uploading` và checkpoint khởi tạo trong CSDL.
     - Đọc stream tệp video và đẩy lên qua `TikTokOfficialAdapter`.
     - Đăng ký callback cập nhật số byte tải lên và phát `sig_upload_progress`.
  2. Tích hợp thuật toán **Exponential Backoff**:
     - Nếu gặp lỗi mạng phân đoạn có thể thử lại, tự động tính toán thời gian chờ:  
       $\text{delay} = 2^{\text{retry\_count}} + \text{random}(1.0, 3.0)$
     - Cập nhật `retry_count` và `next_retry_at` vào CSDL.
  3. Tích hợp cơ chế Reconcile: Khi timeout ở bước xác nhận, gọi hàm đối soát trước khi quyết định đánh dấu thất bại.
- **Đầu ra bàn giao:**
  - `application/workers/video_upload_worker.py`
  - Unit test `tests/unit/test_video_upload_worker.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Tải lên tệp video mẫu thành công, tín hiệu tiến độ % tăng dần đều đặn (0% -> 100%).
  - [ ] Mô phỏng rớt mạng ở chunk thứ 2: Worker thực hiện retry với thời gian chờ lũy thừa chính xác.
  - [ ] Không bao giờ tự động thử lại các lỗi thuộc nhóm chính sách hoặc token không hợp lệ.

