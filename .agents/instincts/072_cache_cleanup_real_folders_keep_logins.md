# 072 — Dọn cache khi thoát: tìm đúng thư mục thật, giữ nguyên đăng nhập

Đã kiểm chứng ngày 2026-11-07 trên @swall.pain (profile 78) thật. Thư mục profile được sao lưu trước tại `D:\tavm_probe\backup78`.

## Lỗi đã sửa
- **Chỉ tìm thấy 1/17 thư mục trình duyệt thật:**
  - `storage_dir` thường là đường dẫn tương đối `profiles/<tên>` không tồn tại; dữ liệu thật nằm ở `<daemon>/profiles/<uuid>`.
  - 101,7 MB cache chưa bao giờ được dọn.
  - Cách sửa: `collect_profile_dirs` dùng `OrbitaLauncher.locate_profile_dir` và bỏ thư mục trùng.
- **Không nhận ra trình duyệt đang chạy:**
  - Trình duyệt mở qua daemon không ghi `.process.lock`, còn nút "Dọn dẹp" không kiểm tra gì cả.
  - Cách sửa: `browser_dirs_in_use()` đọc `--user-data-dir` từ dòng lệnh tiến trình chrome/orbita (psutil). Thư mục đang dùng thì bỏ qua.
- **Lệnh quét `*.tmp` chạy đệ quy vào cả `Local Storage` / `IndexedDB`:** giờ không bao giờ đi vào `PROTECTED_DIRS`.

## Bằng chứng thật (profile 78)
- Trình duyệt đang chạy: bộ dọn trả danh sách rỗng. Đóng trình duyệt: nó nhận đúng thư mục `<daemon>/profiles/1e555ac7-…`.
- Dọn được 5,3 MB, 2 thư mục cache.
- Cookie (`Network/Cookies`), `Local State` (khoá giải mã cookie), `Preferences`, `Login Data`, `Local Storage`, `IndexedDB`, `Session Storage`: hash không đổi. Cookie trong CSDL (`cookies_json`, `cookies_browser`): không đổi.
- Mở lại trình duyệt: `/passport/web/account/info/` báo `logged_in=True` cho `swall.pain`.
  - Cookie `sessionid` là HttpOnly nên `document.cookie` không thấy, đó là bình thường.

## Quy tắc
- Mọi tính năng dọn file trong profile đều phải đi qua `collect_profile_dirs` (tự bỏ qua trình duyệt đang chạy) và `BrowserCacheCleaner` (chỉ xoá `PURGEABLE_CACHE_DIRS` cùng file tạm nằm ngoài các thư mục phiên đăng nhập).
- Khi CDP báo "Cannot find default execution context": trang đang điều hướng, cần chờ lâu hơn rồi đọc lại.
