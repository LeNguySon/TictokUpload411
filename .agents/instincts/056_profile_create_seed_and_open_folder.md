# Instinct 056: Tạo hồ sơ, nạp cookie khi mở trình duyệt, mở thư mục hồ sơ (2026-11-06)

## Lỗi đã vá (test: `tests/unit/test_profile_create_launch_and_seed.py`)
1. Tạo hàng loạt gán proxy = "proxy cuối bảng" ⇒ sai proxy (proxy đã có / trùng) và proxy ngẫu nhiên cho dòng sai
   định dạng. Dùng `ProxyRepository.import_line(line) -> id | None`. Không bao giờ lấy `list_all()[-1]` làm "id vừa tạo".
2. Nhánh offline của Add/Bulk Add sinh uuid 2 lần ⇒ thư mục rỗng mồ côi mỗi hồ sơ.
3. Mỗi lần mở trình duyệt ghi đè cookie nhập (INSERT OR REPLACE) lên phiên trình duyệt đã làm mới ⇒ có thể bị
   đăng xuất. Dùng `BrowserCookieInjector.seed_profile_cookies(dir, cookie)`: chỉ ghi 1 lần cho mỗi giá trị cookie
   (marker `tavm_cookie_seed.sha256` = SHA-256, không chứa cookie); người dùng sửa cookie ⇒ ghi lại 1 lần.
4. Khởi chạy qua SDK (nhánh chính) không nạp cookie ⇒ `launch_via_gologin_sdk(cookie_raw=...)` seed vào
   `DAEMON_PROFILES_DIR/<uuid>` + post cho daemon trước `gl.start()`.
5. "Mở Thư Mục Hồ Sơ": `resolve_profile_dir` TẠO thư mục ⇒ mở thư mục rỗng. Dùng `OrbitaLauncher.locate_profile_dir`
   (không tạo gì); menu phát `open_profile_folder_requested(int id)`.

## Kiểm chứng thật
- `scratch/perf/e2e_cookie_probe.py <chrome.exe>`: Chrome thật đọc được cookie đã seed (value plaintext,
  encrypted_value rỗng) và giữ phiên đã làm mới khi mở lại ⇒ PASS.
- **Orbita không chạy độc lập**: thiếu `orbita.config` (do daemon tạo) ⇒ "License initialization aborted (403)".
  Nhánh dự phòng gọi thẳng `chrome.exe` vì vậy thất bại với hồ sơ chưa từng chạy qua daemon. Không vượt qua kiểm
  tra bản quyền của nhà cung cấp; đường mở đúng là qua SDK/daemon.
