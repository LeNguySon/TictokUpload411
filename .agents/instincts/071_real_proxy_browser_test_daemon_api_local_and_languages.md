# 071 — Test với proxy thật: trình duyệt có proxy không khởi động được, ngôn ngữ bịa

Đã kiểm chứng ngày 2026-11-07 với 4 proxy HTTP thật ở Mexico City (MX). Các lỗi nằm trong daemon của repo SDK, commit `a0f8529`.

## Cách test (dùng lại được, không cần tài khoản TikTok)
- `D:\tavm_probe\live_real_proxies.py`: nhập proxy qua `import_line`, chạy `ProxyService.check_proxy` (sống/chết, độ trễ, IP ra, quốc gia, kiểm tra leak), rồi gọi thử TikTok qua proxy, không kèm cookie.
- `D:\tavm_probe\live_browser_proxy.py`:
  - Tạo profile `ZZTEST` qua `create_real_gologin_profile` với proxy.
  - Khởi chạy bằng `launch_via_gologin_sdk` (headless).
  - Đo bên trong trình duyệt: IP (ipify), `Intl` timezone, `navigator.languages`, IP lộ qua WebRTC (STUN).
  - Cuối cùng xoá profile thử khỏi daemon và ổ đĩa.
- Thông tin đăng nhập proxy chỉ truyền qua biến môi trường `TAVM_TEST_PROXIES`. Không ghi vào repo, không in ra.
- Daemon ghi log ra stdout, mà phần đó đã mất. Muốn biết vì sao trình duyệt chết thì giữ lại profile (`KEEP=1`) và đọc `profiles/<uuid>/chrome_debug.log`.

## Lỗi đã sửa (trong daemon)
- **Mọi profile có proxy đều không khởi động được:**
  - Nhánh proxy truyền `--host-resolver-rules=MAP * ~NOTFOUND,…` nhưng thiếu `api.local`.
  - Orbita kiểm tra giấy phép bằng cách gọi `http://api.local:7654` → `ERR_NAME_NOT_RESOLVED` → Chrome thoát.
  - Từ phía app: `GoLogin.start` mất 30 giây (đúng timeout của SDK), sau đó cổng debug từ chối kết nối.
  - Cách sửa: `browser_host_resolver_rules()` ánh xạ `api.local` về `127.0.0.1` trước tiên.
- **`suggest_accept_languages` tự bịa mã `<cc>-<CC>`:** MX ra `mx-MX`, AR ra tiếng Ả Rập, CO ra tiếng Corse.
  - Cách sửa: bảng quốc gia → ngôn ngữ chính. Quốc gia không có trong bảng thì dùng `en-US`.

## Kết quả sau khi sửa (cả 4 proxy)
- Khởi động 1,7–2,3 giây.
- IP trong trình duyệt = IP proxy. Múi giờ America/Mexico_City.
- `languages` = `es`, `es-MX`, `en`. Chrome tự đặt `es` lên đầu vì không có giao diện `es-MX`.
- WebRTC chỉ thấy IP proxy, không lộ IP máy.

## Lưu ý vận hành
- Daemon đang chạy là `target/release/gologin-cli.exe`, đã copy thành `dist_standalone/.../bin/sammonny-daemon.exe`.
  - Bản trước được sao lưu thành `sammonny-daemon.exe.bak-before-apilocal-fix`.
  - Khởi động bằng `Start-Process` với cwd là thư mục gốc repo SDK, cổng 7654/36912.
- Không dùng `cargo fmt -p gologin-server`: crate này chưa theo chuẩn rustfmt, nên lệnh sẽ định dạng lại hàng nghìn dòng không liên quan. Chỉ format file mình sửa, hoặc không format.

## Ngày 2026-11-07 (chiều): múi giờ phân tích, rebuild exe, kiểm chứng tuyên bố của agent khác
- TikTok trả giờ phân tích theo đúng `tz_offset` mà request gửi lên. Trên profile 78: +7h cho giờ vàng 06:00, 0 cho 00:00, −6h cho 17:00.
  - Luôn dùng `request_time.local_utc_offset_seconds()`. Có test cấm gán cứng `tz_offset=` / `time_offset=` trong `src/`.
- Kiểm tra "video X đã đăng" phải duyệt ĐỦ các trang `item_list` (`_list_all_items`). Trang đầu không sắp theo ngày nên dễ báo nhầm "không có".
  - oEmbed (`/oembed`) không trả tiêu đề qua kênh này, nên không dùng được để kiểm chứng.
- Rebuild exe: dùng worktree sạch, chạy `packaging/build_exe.py app`, chạy thử (PrintWindow chụp được nội dung cửa sổ dù bị che, chờ 60 giây, đọc log), rồi thay `dist/SonBetaPro`.
  - KHÔNG để shell đứng bên trong `dist/SonBetaPro` khi `mv` (lỗi "Device or resource busy").
  - KHÔNG nối `git worktree remove` sau lệnh `&&` của bước copy: copy lỗi thì bản build vẫn bị xoá theo.
