# Sprint 1: Hạ Tầng Cốt Lõi, Cơ Sở Dữ Liệu & Security Vault

- **Thời lượng dự kiến:** Tuần 1
- **Mục tiêu chính:** Thiết lập khung dự án, hoàn thiện kết nối và schema 24 bảng SQLite với ràng buộc khóa ngoại, xây dựng Windows DPAPI Vault và hệ thống logging bảo vệ bí mật.

---

### `TSK-01-ENV`: Thiết Lập Project Skeleton, CI & Công Cụ Kiểm Soát Chất Lượng
- **Loại hình:** Hạ tầng / Tooling
- **Tiền đề:** Không
- **Mô tả công việc:**
  1. Tạo toàn bộ cây thư mục mã nguồn theo kiến trúc Clean Architecture: `app/`, `presentation/`, `application/`, `domain/`, `infrastructure/`, `tests/`.
  2. Tạo các tệp `__init__.py` rỗng tại tất cả các gói.
  3. Soạn thảo `pyproject.toml` định nghĩa cấu hình cho `ruff`, `mypy --strict`, `pytest`.
  4. Soạn thảo `requirements.txt` với các phiên bản ghim chặt.
- **Đầu ra bàn giao:**
  - `pyproject.toml`
  - `requirements.txt`
  - Cấu trúc thư mục mã nguồn chuẩn.
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Chạy `python -m venv .venv` và cài đặt `requirements.txt` thành công 100%.
  - [ ] Chạy `ruff check .` trả về exit code 0.
  - [ ] Chạy `mypy .` trả về exit code 0.

---

### `TSK-02-MIG`: Triển Khai 24 Bảng SQLite Migration & Database Connection Manager
- **Loại hình:** Cơ sở dữ liệu / Hạ tầng
- **Tiền đề:** `TSK-01-ENV`
- **Mô tả công việc:**
  1. Xây dựng module `infrastructure/database/connection.py` quản lý kết nối SQLite thread-safe, tự động thực thi:
     ```sql
     PRAGMA foreign_keys = ON;
     PRAGMA journal_mode = WAL;
     PRAGMA synchronous = NORMAL;
     ```
  2. Port toàn bộ DDL từ các file migration nguồn (`init_schema.py`, `tiktok_schema.py`, `vault_credentials.py`, runtime DDL) thành bộ mã migration độc lập trong `infrastructure/database/migrations/`.
  3. Tạo migration runner kiểm tra phiên bản qua bảng `system_metadata`.
- **Đầu ra bàn giao:**
  - `infrastructure/database/connection.py`
  - `infrastructure/database/migrations/migration_runner.py`
  - `infrastructure/database/migrations/schemas.py`
  - Unit test `tests/unit/test_migrations.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Chạy migration trên file CSDL tạm tạo đúng 24 bảng.
  - [ ] Kiểm tra `PRAGMA table_info` và `foreign_key_list` khớp 100% với đặc tả `docs/02_specifications/database_schema.md`.
  - [ ] Test chèn dữ liệu vi phạm khóa ngoại (ví dụ: tạo profile với `project_id` không tồn tại) phải ném ngoại lệ `sqlite3.IntegrityError`.

---

### `TSK-03-REPO`: Xây Dựng Base Repository & Repositories Chuyên Biệt
- **Loại hình:** Cơ sở dữ liệu / Kho lưu trữ
- **Tiền đề:** `TSK-02-MIG`
- **Mô tả công việc:**
  1. Hiện thực hóa `BaseRepository` cung cấp Context Manager quản lý Transaction:
     ```python
     with repo.transaction() as cur:
         ...
     ```
  2. Xây dựng `ProfileRepository`:
     - Truy vấn danh sách profiles (có phân trang, sắp xếp, tìm kiếm theo tên/tiktok_id).
     - Lọc theo project, trạng thái, proxy.
     - Hàm soft-delete (`is_trashed = 1`) và restore.
  3. Xây dựng `QueueRepository`:
     - Thêm video vào queue, lấy danh sách pending jobs theo lịch đăng.
     - Cập nhật checkpoint và trạng thái atomic.
  4. Xây dựng `StatsRepository`:
     - Ghi nhận snapshot chỉ số vào `statisticTable` và `videoTables`.
- **Đầu ra bàn giao:**
  - `infrastructure/database/repositories/base_repository.py`
  - `infrastructure/database/repositories/profile_repository.py`
  - `infrastructure/database/repositories/queue_repository.py`
  - `infrastructure/database/repositories/stats_repository.py`
  - Unit test `tests/unit/test_repositories.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] 100% câu lệnh SQL sử dụng Parameterized Query (`?`), không cộng chuỗi.
  - [ ] Unit test chứng minh transaction tự rollback khi xảy ra exception ở giữa thao tác ghi.

---

### `TSK-04-VAULT`: Triển Khai Windows Credential Manager DPAPI Vault Adapter
- **Loại hình:** Bảo mật / Hệ điều hành
- **Tiền đề:** `TSK-01-ENV`
- **Mô tả công việc:**
  1. Xây dựng lớp `WindowsCredentialVault` sử dụng thư viện `keyring` giao tiếp với Windows Credential Manager.
  2. Định nghĩa namespace lưu trữ: `TikTokUploadManager.Profile.<profile_id>`.
  3. Đóng gói các hàm: `save_oauth_tokens(profile_id, access_token, refresh_token, client_secret)`, `get_oauth_tokens(profile_id)`, `clear_tokens(profile_id)`.
- **Đầu ra bàn giao:**
  - `infrastructure/credentials/windows_vault.py`
  - Unit test `tests/unit/test_windows_vault.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Lưu trữ và đọc lại token chính xác 100%.
  - [ ] Mở ứng dụng Windows Credential Manager (Control Panel) thấy key được lưu đúng tên namespace.
  - [ ] Không có bất kỳ token nào bị ghi vào file SQLite hay file cấu hình.

---

### `TSK-05-SEC-LOG`: Thiết Lập Redaction Structured Logging System
- **Loại hình:** Bảo mật / Logging
- **Tiền đề:** `TSK-01-ENV`
- **Mô tả công việc:**
  1. Xây dựng `RedactionFilter` kế thừa `logging.Filter` sử dụng regular expressions để nhận diện:
     - Bearer tokens, JWT tokens (`ey...`)
     - Chuỗi mật khẩu (`password=...`)
     - Cookie JSON (`sessionid=...`, `sid_guard=...`)
  2. Cấu hình logger xuất ra đồng thời Console và tệp `logs/app.log` có cơ chế xoay vòng (RotatingFileHandler, max 10MB x 5 files).
- **Đầu ra bàn giao:**
  - `infrastructure/logging/redaction_logger.py`
  - Unit test `tests/unit/test_redaction_logger.py`
- **Tiêu chí nghiệm thu (DoD):**
  - [ ] Đưa chuỗi chứa cookie và access token vào câu log, file log xuất ra chuỗi `***REDACTED***`.
  - [ ] Định dạng log chuẩn JSON/Text có đầy đủ timestamp, thread_name, log_level, module.

