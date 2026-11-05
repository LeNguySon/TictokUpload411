# Instinct 040: Upload Pool, psutil Scans, Debounce & Test Safety (UI Responsiveness P2)

Kế hoạch: `docs/03_work_breakdown/ui_responsiveness_fix_plan.md` (Sprint P2 = T8–T10). Tiếp nối 036, 038.

## 1. Upload chạy trên pool riêng (T8)
- `ThreadPoolManager.dispatch_upload(worker)` → `upload_thread_pool()` (cấp module, parent = QApplication). **Mọi `UploadWorker` phải đi qua `dispatch_upload`**; `dispatch()` dành cho worker ngắn (status sync, metrics, proxy check, import). Có test tĩnh trong `tests/unit/test_ui_responsiveness_p2.py` bảo vệ điều này.
- `set_max_threads(n)` = số upload đồng thời; pool chung luôn giữ ≥ `MIN_GENERAL_THREADS` (4) luồng.
- Pool là tài nguyên toàn tiến trình: test nào đổi kích thước phải trả về mặc định (`set_max_threads(10)`).

## 2. psutil: chỉ quét một lượt mỗi lúc, và không đọc cmdline của mọi tiến trình (T9)
- `psutil.process_iter()` chạy song song trên Windows ⇒ access violation. `_scan_psutil_for_profile` dùng `_PSUTIL_SCAN_LOCK` + `_PSUTIL_SCAN_CACHE` cấp module (TTL 2,5 s), dùng chung cho mọi `OrbitaLauncher`.
- **Không bao giờ `process_iter(["name", "cmdline"])`**: đọc command line của ~270 tiến trình tốn ~2 s mỗi lượt (lặp mỗi 3 s ⇒ CPU nền liên tục, GIL làm GUI khựng ~27 ms). Lấy `["name"]` rồi `proc.cmdline()` chỉ cho chrome/orbita: ~13 ms (lượt đầu tiên của tiến trình ~1 s do psutil khởi tạo cache).
- Đã khai báo lại `psutil>=5.9.0` trong `requirements.txt` và `pyproject.toml`.

## 3. Debounce & cache phía UI (T10)
- Ô tìm kiếm: lọc sau 200 ms ngừng gõ (`_apply_profile_filter` / `_apply_video_filter`); xóa trống thì hiện lại ngay; bộ lọc được áp lại sau mỗi lần nạp bảng. Timer nối qua `lambda: self._apply_...()` để có thể patch trong test.
- Avatar không tồn tại được cache âm 30 s (`MISSING_AVATAR_TTL_S`); `forget_avatar(path)` khi `profile_updated` mang `avatar_path` mới.
- Thông báo upload hoàn tất/thất bại gộp trong 1,5 s thành một InfoBar mỗi loại; một sự kiện đơn vẫn giữ nội dung chi tiết.
- Test chờ debounce: `process_events_until(lambda: not win._profile_search_timer.isActive())` (PyQt6 không có `QTest.qWaitFor`).

## 4. AN TOÀN KHI CHẠY TEST: không được kill trình duyệt thật
- `BrowserProcessSupervisor.cleanup_orphan_browsers()` (không truyền danh sách) quét OS và **kill mọi chrome/orbita có chữ "profiles" trong command line** mà không có lock file. Khi venv có psutil, các test bấm "Dọn dẹp trình duyệt" sẽ chạy thật trên máy dev.
- `tests/conftest.py::never_kill_real_browsers` (autouse) chặn trường hợp này; test có danh sách orphan giả hoặc psutil giả vẫn chạy logic thật. Không gỡ fixture này.
- Rủi ro sản phẩm còn mở: tiêu chí `"profiles" in cmdline` quá rộng — trình duyệt GoLogin/antidetect khác của người dùng có thể bị coi là "mồ côi" và bị kill khi bấm Dọn dẹp.
