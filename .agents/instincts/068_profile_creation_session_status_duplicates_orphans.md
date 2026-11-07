# 068 — Tạo profile (đơn lẻ + hàng loạt): trạng thái, trùng tài khoản, profile mồ côi

Đã kiểm chứng ngày 2026-11-07: chạy thật với daemon trên bản sao CSDL. Profile thử đặt tên `ZZTEST_*` và được xoá khỏi daemon và ổ đĩa sau khi chạy.

## Lỗi đã gặp
- **Trạng thái sai:** đường daemon gắn `LIVE` cho mọi cookie. Profile chỉ có `msToken` (chưa đăng nhập) vẫn hiện LIVE. Đường dự phòng thì dùng một quy tắc khác.
- **Nhập trùng tài khoản:** nhập cùng tài khoản 2 lần tạo ra 2 profile. Kết quả là 2 trình duyệt với 2 vân tay khác nhau cùng đăng nhập 1 tài khoản TikTok.
- **Profile mồ côi:** nếu một bước lỗi sau `gl.create`, nhánh dự phòng tạo thêm profile local, còn profile trên daemon bị bỏ lại.
- **Daemon tắt khi tạo hàng loạt:** mỗi dòng lại gọi `ensure_daemon_running`, tốn tới ~6 giây mỗi dòng.
- Nhánh dự phòng bị chép y hệt ở 2 dialog.

## Quy tắc
- Trạng thái ban đầu chỉ dùng `_initial_status(cookie)`, dựa trên `BrowserCookieInjector.has_session_cookie()` (`sessionid` / `sessionid_ss` / `sid_tt`, cả chuỗi header lẫn JSON).
- `create_real_gologin_profile`: mọi bước sau `gl.create` nằm trong `_finish_daemon_profile`. Nếu lỗi thì `gl.delete(uuid)` rồi raise.
- Profile local (khi không có daemon) chỉ tạo qua `GoLoginSyncService.create_local_profile` (uuid, thư mục, vân tay riêng).
- `import_profiles`: kiểm tra daemon 1 lần cho cả lô (`ensure_daemon=False` cho từng dòng). Bỏ qua tài khoản đã có, so theo `name` / `username_on_tiktok` (chữ thường, bỏ `@`), và báo qua `duplicate_rows`.
- Khi thử nghiệm trên daemon thật: luôn dọn dẹp trong khối `finally` (`gl.delete` + xoá thư mục).
