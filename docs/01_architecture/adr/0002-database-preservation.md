# ADR-0002: Bảo Tồn Nguyên Trạng 24 Bảng CSDL SQLite Kế Thừa

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-11-04
- **Người phê duyệt:** Lead Database Architect
- **Phạm vi:** Infrastructure Layer / Storage

---

### Bối Cảnh & Vấn Đề (Context)
Hệ thống kế thừa schema CSDL từ dự án tiền nhiệm (`Gloglin2609`) bao gồm 18 bảng định nghĩa trong các migration (`init_schema.py`, `tiktok_schema.py`, `vault_credentials.py`) và 6 bảng được tạo runtime bởi các engine DDL. Một số cột trong schema có cách đặt tên không đồng nhất (ví dụ: `views_month`, `statistic_date_update`, `appealViolateDate`, `is_trashed`).

Câu hỏi đặt ra: Có nên chuẩn hóa lại (normalize / rename) tên các bảng và cột sang chuẩn `snake_case` thuần nhất hay giữ nguyên?

---

### Quyết Định (Decision)
**Bảo tồn nguyên trạng 100% cấu trúc, tên bảng, tên cột và ràng buộc của cả 24 bảng CSDL SQLite kế thừa.**

Đồng thời áp dụng các nguyên tắc vận hành:
1. Luôn kích hoạt: `PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;`.
2. Tầng Domain Models sẽ ánh xạ các tên cột legacy thành thuộc tính Python chuẩn, đóng gói sự không đồng nhất này bên trong tầng Repositories.

---

### Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực**:
  - Tương thích tuyệt đối với các script migration gốc và khả năng tương thích ngược với file CSDL `gloglin.db` nếu có.
  - Không phá vỡ các truy vấn SQL hoặc logic đã được kiểm chứng trong hệ thống cũ.
- **Tiêu cực / Rủi ro**:
  - Mã nguồn trong Repositories phải quản lý một số tên trường kiểu camelCase (`appealViolateDate`, `ttl_violations`). Điều này được giải quyết bằng các lớp Repository chuyên biệt.

