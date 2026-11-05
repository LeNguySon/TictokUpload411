# Instinct 028 — Bulk TikTok Account Format Customization & Zero-Click Cookie Injection
## Ngày ghi nhận: 2026-11-05

## Bối cảnh kỹ thuật
- Khi nhập hàng loạt tài khoản TikTok MMO từ các tệp dữ liệu của người dùng, mỗi nguồn cung cấp (seller/tool) có thể có cấu trúc cột khác nhau (8 trường: `User|Pass|Cookie|Email|Passmail|RefreshToken|ClientId|CookieEmail`, hoặc 5 trường cũ, hoặc thứ tự tùy biến).
- Ngoài ra, nếu chỉ lưu chuỗi cookie dạng string thô vào CSDL mà không nạp vào hệ thống Cookie SQLite của trình duyệt (GoLogin/Orbita), khi người dùng mở profile lên, trình duyệt sẽ ở trạng thái trắng (guest) và bắt người dùng phải đăng nhập thủ công lại.

## Nguyên nhân gốc rễ & Thách thức
1. **Sự không đồng nhất về định dạng dữ liệu (Data Format Heterogeneity)**: Cần một parser có khả năng ánh xạ linh hoạt dựa theo danh sách token (`{user}`, `{pass}`, `{cookie}`, `{email}`, `{pass_mail}`, `{refresh_token}`, `{client_id}`, `{cookie_email}`) và cho phép người dùng tùy chọn dấu phân cách (`|`, `:`, `Tab`, `,`).
2. **Cấu trúc Cookie Chromium phức tạp (Chromium Cookie Structure)**: Cookie của Chromium không phải là chuỗi string thô mà gồm nhiều trường: `name`, `value`, `domain` (phải có tiền tố `.tiktok.com`), `path`, `secure=True`, `httpOnly=True` cho các session cookie (`sessionid`, `sid_tt`, `sid_guard`...). Nếu thiếu cờ hoặc sai domain, trình duyệt sẽ từ chối cookie và bắt đăng nhập lại.
3. **Tuân thủ AgentShield**: Mật khẩu TikTok, mật khẩu Email, session token tuyệt đối không được hiển thị trần trụi (plaintext) trong bảng xem trước (preview table).

## Giải pháp kiến trúc chuẩn
1. **Bộ Phân Giải Đa Hình (`ProfileImportParser`)**:
   - Quản lý các Preset (`mmo_8_fields`, `legacy_5_fields`, `basic_3_fields`, `account_mail_4_fields`, `cookie_only`) cùng chế độ Custom Template.
   - Hỗ trợ bí danh (aliases) chuẩn hóa tên trường tiếng Việt và tiếng Anh.
2. **Bộ Nạp Cookie Trình Duyệt (`BrowserCookieInjector`)**:
   - `parse_cookie_string`: Tự động nhận diện chuỗi `key=value; ...` hoặc JSON array, gán đúng domain `.tiktok.com`, `path="/"`, `secure=True`, và `httpOnly=True` cho `_HTTP_ONLY_COOKIES`.
   - `inject_to_gologin`: Gọi `gl.post_cookies(cookie_items, profile_id=uuid)` để SDK Daemon ghi trực tiếp vào Network/Cookies của profile GoLogin.
   - `inject_to_chromium_sqlite`: Dự phòng ghi trực tiếp vào tệp SQLite `Network/Cookies` của Orbita.
3. **AgentShield Masking trên Giao Diện**:
   - `BulkAddProfileDialog` tự động mask mật khẩu thành `••••••••` và cookie thành `sessionid=xxxx*** (N ký tự)`.
   - Lưu trữ song song vào `WindowsCredentialVault` thông qua mã hóa Windows DPAPI.

