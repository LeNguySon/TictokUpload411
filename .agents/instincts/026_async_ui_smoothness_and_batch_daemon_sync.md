# Bản Năng 026: Xử Lý Triệt Để Lỗi Treo Giật Giao Diện (UI Freezing) Bằng Batch Daemon API & QThreadPool Async Worker

## Bối Cảnh (Context)
Khi số lượng hồ sơ trình duyệt trong TikTok Manager tăng lên (từ vài hồ sơ lên 63+ hồ sơ), ứng dụng gặp tình trạng giao diện bị đơ, giật lag (Windows báo "(Not Responding)") mỗi khi khởi động hoặc định kỳ mỗi 1.5 giây.
Nguyên nhân gốc rễ (Root Cause Analysis):
1. Phương thức `_sync_active_profile_statuses()` chạy định kỳ trên `QTimer(interval=1500)` trực tiếp trên Qt Main Thread.
2. Với mỗi hồ sơ, hàm `OrbitaLauncher.is_profile_running()` thực hiện tuần tự kiểm tra kết nối HTTP đến Daemon API và quét `psutil.process_iter()`. Tổng thời gian cho 63 profiles là **2.85s - 4.35s**.
3. Vì thời gian xử lý đồng bộ trên Main Thread (4.35s) lớn hơn chu kỳ timer (1.5s), vòng lặp sự kiện Qt (Event Loop) bị chiếm dụng 100%, gây ra hiện tượng UI Freezing và Starvation hoàn toàn.
4. Tại hàm `refresh_profiles()`, việc duyệt đồng bộ 63 hồ sơ khiến việc mở màn hình chính hoặc chọn dự án bị đứng hình 4 giây.

## Giải Pháp Kỹ Thuật Chuẩn ECC (Resolution & Architecture)
1. **Chuyển Đổi Sang Tác Vụ Bất Đồng Bộ (Async Offloading)**:
   - Toàn bộ tác vụ quét trạng thái hồ sơ được chuyển sang `ProfileRuntimeSyncWorker` chạy trên nền `QThreadPool`.
   - Kết quả chênh lệch trạng thái (Delta Map: `{profile_id: new_status}`) được phát tín hiệu `statuses_updated` về Main Thread thông qua Qt Signals & Slots (`Qt.QueuedConnection`).
   - Main Thread chỉ cập nhật đúng các ô cell (cột 12: `StatusBadgeDelegate`) và bản ghi SQLite có trạng thái thay đổi trong thời gian `< 0.001s`, duy trì độ mượt 60 FPS.
2. **Kỹ Thuật Batch Daemon Inspection (145x Speedup)**:
   - Thêm phương thức `OrbitaLauncher.batch_check_profiles_running(profiles)`.
   - Thay vì gửi 63 requests HTTP riêng lẻ, gửi đúng **1 HTTP request** duy nhất tới `/api/v1/profiles` thông qua `SamMonnyDaemonClient.list_profiles()` (thời gian phản hồi chỉ 28ms) kết hợp kiểm tra `is_port_open(7654)` siêu tốc (0.2ms).
3. **Phòng Ngừa Lỗi Garbage Collection & C++ Object Deletion**:
   - Khi tạo `QRunnable` worker và `WorkerSignals`, gán parent `QObject` cho signals và đặt `setAutoDelete(False)` để tránh việc C++ xóa nhầm instance signals khi worker thread đang phát tín hiệu.
   - Thêm `thread_pool.pool.waitForDone(300)` trong `closeEvent` để thu hồi thread an toàn khi tắt app.
4. **An Toàn Mã Hóa Console UTF-8 Trên Windows**:
   - Tại `main.py`, thiết lập `sys.stdout.reconfigure(encoding="utf-8")` và `sys.stderr.reconfigure(encoding="utf-8")` để tránh `UnicodeEncodeError` khi in emoji hoặc tiếng Việt có dấu.
   - Trong `RedactionFilter`, chỉ áp dụng redaction cho đối tượng dạng `str`, tuyệt đối không chuyển đổi `int`/`float` thành chuỗi trong `record.args` để không phá vỡ các chuỗi định dạng `%d`, `%f`.

## Quy Chuẩn Bắt Buộc (Mandatory Rules)
- **Tuyệt đối không chạy I/O, quét process psutil, hoặc gọi HTTP request trên Qt Main GUI Thread**. Mọi tác vụ tốn trên 16ms bắt buộc phải đưa vào `QRunnable` worker qua `ThreadPoolManager.instance().dispatch(worker)`.
- Khi cập nhật giao diện dạng bảng có nhiều dòng, chỉ cập nhật cell có trạng thái thay đổi (delta update), tránh gọi `load_profiles()` hoặc render lại toàn bộ bảng liên tục.
