# ADR-0005: Tích Hợp SamMonny SDK Theo Chế Độ Ủy Quyền Chính Thức

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-11-04
- **Người phê duyệt:** Lead Compliance & SDK Architect
- **Phạm vi:** Infrastructure / SDK Adapter

---

### Bối Cảnh & Vấn Đề (Context)
SDK `sammonny` 1.8.1 (nằm tại `D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\sdk\python`) hỗ trợ nhiều chế độ hoạt động: từ đăng bài qua Official OAuth Direct Post, cho đến các phương thức dùng cookie, headless browser, hoặc can thiệp signature. 

Việc sử dụng các luồng cookie trái phép tiềm ẩn nguy cơ cao bị khóa tài khoản hàng loạt (Checkpoint/Ban), rò rỉ session và vi phạm điều khoản dịch vụ của nền tảng.

---

### Quyết Định (Decision)
**Chỉ sử dụng chế độ Official API (`TikTokPublisherAdapter` & `TikTokDirectPostClient`) thông qua OAuth Token được người dùng cấp quyền hợp lệ.**

Quy tắc bất khả xâm phạm:
1. Không import hoặc gọi các hàm cookie import hay headless automation của SDK.
2. Khi tài khoản hết hạn token hoặc thiếu quyền hạn (Capability), adapter chuyển trạng thái sang `manual_required` và yêu cầu người dùng xác nhận trên giao diện. Tuyệt đối không tự động fallback sang luồng cookie lậu.
3. Mọi thao tác tải lên đều qua endpoint phân đoạn chunk chính thức kèm cơ chế kiểm tra đối soát (`reconcile`).

---

### Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực**:
  - Bảo vệ 100% tài sản tài khoản của người dùng khỏi nguy cơ bị phạt thuật toán hoặc khóa vĩnh viễn.
  - Tuân thủ đầy đủ các chuẩn mực phân phối nội dung an toàn.
- **Tiêu cực / Rủi ro**:
  - Người dùng phải thực hiện bước cấp quyền OAuth ban đầu cho các tài khoản.

