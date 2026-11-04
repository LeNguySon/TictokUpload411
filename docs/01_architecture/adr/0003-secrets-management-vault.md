# ADR-0003: Quản Lý Bí Mật Bằng Windows Credential Manager (DPAPI)

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-11-04
- **Người phê duyệt:** Lead Security Engineer
- **Phạm vi:** Security / Infrastructure Layer

---

### Bối Cảnh & Vấn Đề (Context)
Các token ủy quyền chính thức của TikTok (OAuth `access_token`, `refresh_token`), `client_secret`, cũng như mật khẩu tài khoản là các thông tin nhạy cảm cấp độ cao nhất. Nếu lưu trực tiếp các bí mật này dưới dạng văn bản rõ (plaintext) trong tệp CSDL SQLite `app.db`, nguy cơ rò rỉ khi người dùng chia sẻ tệp DB hoặc bị phần mềm độc hại trích xuất là rất lớn.

---

### Quyết Định (Decision)
**Tuyệt đối không lưu Access Token và Bí mật xác thực dạng plaintext trong SQLite.**  
Thay vào đó, sử dụng **Windows Credential Manager** thông qua **Data Protection API (DPAPI)** với thư viện chuẩn `keyring`.

Nguyên tắc:
- Mỗi profile sở hữu một secret entry trong Windows Vault dưới namespace:  
  `TikTokUploadManager.Profile.<profile_id>`
- Dữ liệu lưu trong Vault được mã hóa đối xứng bằng khóa gắn liền với phiên đăng nhập của người dùng Windows hiện tại.
- Tệp SQLite chỉ lưu trạng thái cờ: `has_authorized_token: BOOLEAN`.

---

### Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực**:
  - Đạt chuẩn bảo mật an ninh **AgentShield Tier-1**.
  - Tệp SQLite có thể sao lưu, di chuyển nội bộ mà không sợ lộ token xác thực.
- **Tiêu cực / Rủi ro**:
  - Không thể copy nguyên file DB sang máy tính khác mà giữ nguyên phiên đăng nhập (người dùng sẽ phải cấp lại quyền trên máy mới). Đây là tính năng bảo mật chủ động, không phải lỗi.

