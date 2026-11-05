# Instinct 049: Checkbox "Dọn cache khi thoát" & cách ly QSettings trong test

## Lỗi cũ (2026-11-05)
- Checkbox footer chỉ gọi `MemoryManager.trim_process_tree_memory(os.getpid())` (giảm RAM của chính tiến trình
  sắp thoát) ⇒ **không dọn cache nào**. Không lưu trạng thái, là `QCheckBox` thô.
- Hiện tại: `closeEvent` → `_clean_cache_on_exit()` → `collect_profile_dirs()` (cache_cleaner.py) → bỏ qua hồ sơ
  đang chạy (`BrowserProcessSupervisor.is_process_running`) → `BrowserCacheCleaner.clean_cache` (giữ cookie/đăng
  nhập/extension). Trạng thái lưu ở key `clean_cache_on_exit`. Test: `tests/unit/test_clean_cache_on_exit.py`.

## Không bao giờ ghi registry thật từ test
- Mọi QSettings của main window đi qua `TikTokManagerMainWindow._settings()`.
- `tests/conftest.py::isolated_ui_settings` (autouse) trỏ `_settings` tới file ini tạm. Một test cũ từng xóa
  `hidden_profile_columns` thật, và lần đầu viết test checkbox đã ghi `clean_cache_on_exit=false` vào registry thật
  (đã khôi phục). Patch phải kéo dài **suốt test**, không chỉ lúc dựng cửa sổ (toggle cũng ghi settings).
- QSettings mới thêm ở chỗ khác ⇒ cũng phải đi qua một điểm truy cập có thể monkeypatch.
