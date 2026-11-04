# ADR-0004: Mô Hình Đa Luồng QThreadPool Và Signal Bus Định Kiểu

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-11-04
- **Người phê duyệt:** Lead Concurrency Engineer
- **Phạm vi:** Application / Presentation Layers

---

### Bối Cảnh & Vấn Đề (Context)
Các thao tác mạng như đồng bộ dữ liệu của 50 profiles hoặc tải lên video dung lượng lớn (100MB - 1GB) theo từng phân đoạn (chunked upload) là các tác vụ I/O tốn nhiều thời gian. Nếu thực thi trên luồng chính (Main Thread), ứng dụng sẽ lập tức bị hệ điều hành gắn nhãn "(Not Responding)" và giao diện bị đóng băng. Hơn nữa, việc tạo không giới hạn `QThread` độc lập cho từng profile có thể gây cạn kiệt tài nguyên mạng và bị TikTok gắn cờ tấn công DoS.

---

### Quyết Định (Decision)
1. Sử dụng **`QThreadPool`** toàn cục với giới hạn số luồng đồng thời tối đa (Bounded Concurrency, mặc định `max_threads = 5`).
2. Mọi tác vụ chạy nền đều được đóng gói dưới dạng **`QRunnable`** kế thừa từ `BaseWorker`.
3. Tích hợp cơ chế **Hủy Hợp Tác (Cooperative Cancellation)** thông qua cờ `is_interruption_requested()`.
4. Toàn bộ luồng giao tiếp ngược về Main Thread đều đi qua một **`AppSignalBus`** duy nhất với các payload là `@dataclass(frozen=True)` định kiểu chặt chẽ.

---

### Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực**:
  - Giao diện mượt mà 100%, không bao giờ xuất hiện hiện tượng đơ giật.
  - Kiểm soát chính xác băng thông mạng và tần suất gọi API của từng tài khoản.
  - Dễ dàng unit test logic worker bằng cách mô phỏng `fake_signals`.
- **Tiêu cực / Rủi ro**:
  - Lập trình viên phải cẩn trọng không giữ tham chiếu con trỏ GUI trong `QRunnable`.

