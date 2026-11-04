# Sprint 5: Tích Hợp Toàn Trình, Kiểm Thử Tải & Đóng Gói Phát Hành

- **Thời lượng dự kiến:** Tuần 5
- **Mục tiêu chính:** Kiểm thử tích hợp toàn trình (E2E), kiểm thử tải 5,000 profiles, kiểm toán an ninh thông tin AgentShield, đóng gói phần mềm thành file chạy độc lập `.exe` và vượt qua chốt chặn GATE 2.

---

### `TSK-17-INT-E2E`: Kiểm Thử Tích Hợp Toàn Trình (End-to-End Testing)
- **Loại hình:** Kiểm thử / QA
- **Tiền đề:** Hoàn thành toàn bộ `TSK-01` đến `TSK-16`
- **Mô tả công việc:**
  1. Viết kịch bản kiểm thử tự động toàn diện sử dụng `pytest-qt`:
     - Khởi tạo ứng dụng -> Import 5 profiles mẫu -> Kiểm tra dữ liệu xuất hiện trên bảng.
     - Kích hoạt đồng bộ chỉ số qua Fake SDK -> Kiểm tra tín hiệu phát ra -> Kiểm tra chỉ số được lưu vào CSDL và cập nhật trên UI.
     - Thêm 2 video vào hàng đợi -> Bắt đầu chạy hàng đợi -> Mô phỏng upload thành công 1 video và lỗi 1 video có retry -> Kiểm tra cập nhật trạng thái cuối cùng.
- **Đầu ra bàn giao:**
  - `tests/integration/test_e2e_workflow.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Toàn bộ kịch bản E2E chạy tự động ở chế độ Headless thành công 100%.
  - [ ] Không xuất hiện lỗi race condition hoặc deadlock trong toàn bộ vòng đời ứng dụng.

---

### `TSK-18-PERF-STRESS`: Kiểm Thử Hiệu Năng & Chống Rò Rỉ Bộ Nhớ (Memory Leak)
- **Loại hình:** Hiệu năng / Stress Test
- **Tiền đề:** `TSK-17-INT-E2E`
- **Mô tả công việc:**
  1. Xây dựng script sinh dữ liệu giả lập (Mock Generator): Tạo 5,000 bản ghi profiles và 1,000 bản ghi video queue trong CSDL SQLite.
  2. Đo lường hiệu năng:
     - Thời gian khởi động ứng dụng (Cold Start Time).
     - Tốc độ cuộn và lọc bảng (FPS và CPU usage).
     - Mức chiếm dụng bộ nhớ RAM (sử dụng thư viện `tracemalloc` hoặc `psutil`).
  3. Chạy vòng lặp worker liên tục trong 2 giờ để kiểm tra rò rỉ bộ nhớ (Memory Leak Check).
- **Đầu ra bàn giao:**
  - `tests/benchmarks/test_performance.py`
  - Báo cáo kết quả đo lường hiệu năng `docs/benchmarks/PERFORMANCE_REPORT.md`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Khởi động ứng dụng nạp 5,000 profiles < 2.0 giây.
  - [ ] Mức chiếm dụng RAM ban đầu < 150MB; sau 2 giờ chạy liên tục không tăng quá 50MB.

---

### `TSK-19-AUDIT`: Đánh Giá An Toàn Thông Tin Chuẩn AgentShield
- **Loại hình:** An ninh / Security Audit
- **Tiền đề:** `TSK-17-INT-E2E`
- **Mô tả công việc:**
  1. Quét tĩnh toàn bộ codebase với công cụ `bandit -r app/ application/ domain/ infrastructure/`.
  2. Quét kiểm tra rò rỉ bí mật trong toàn bộ lịch sử Git và các file cấu hình.
  3. Kiểm tra file log `logs/app.log` khi chạy thực tế có để lọt bất kỳ token hay mật khẩu nào không.
  4. Kiểm tra memory dump của tiến trình Python bằng công cụ hex editor để đảm bảo secrets không bị cache trần trong biến toàn cục.
- **Đầu ra bàn giao:**
  - Báo cáo an ninh `docs/05_security/SECURITY_AUDIT_REPORT.md`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Kết quả quét `bandit`: 0 High, 0 Medium issues.
  - [ ] 100% secrets được cô lập trong Windows DPAPI Vault.

---

### `TSK-20-RELEASE`: Đóng Gói Ứng Dụng (PyInstaller) & Hoàn Thiện Runbook
- **Loại hình:** Đóng gói / Release
- **Tiền đề:** `TSK-18-PERF-STRESS`, `TSK-19-AUDIT`
- **Mô tả công việc:**
  1. Soạn thảo tệp cấu hình đóng gói `build.spec` cho PyInstaller:
     - Bao gồm toàn bộ assets, icons, fonts của Fluent Widgets.
     - Ẩn cửa sổ console đen (`--noconsole`).
     - Đặt icon ứng dụng chính thức.
  2. Thực thi lệnh đóng gói tạo file `.exe` độc lập cho Windows 64-bit.
  3. Kiểm thử khởi chạy file `.exe` trên máy Windows 10/11 sạch không có cài đặt Python.
  4. Hoàn thiện tài liệu hướng dẫn vận hành cho người dùng cuối (`docs/04_guides/operational_runbook.md`).
- **Đầu ra bàn giao:**
  - `build.spec`
  - `dist/TikTokUploadManager.exe`
  - `docs/04_guides/operational_runbook.md`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] File `.exe` khởi chạy mượt mà trên môi trường Windows sạch.
  - [ ] Vượt qua **GATE 2: Nghiệm thu bàn giao và phát hành chính thức**.

