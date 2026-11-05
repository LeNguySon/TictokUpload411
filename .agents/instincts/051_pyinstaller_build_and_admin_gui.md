# Instinct 051: Build exe (PyInstaller) & app Admin cấp key

## Bẫy khi build (2026-11-05)
- `collect_all("sammonny"/"curl_cffi"/...)` kéo theo hook PyQt5 ⇒ PyInstaller dừng ("multiple Qt bindings").
  Luôn `excludes=["PyQt5", "PySide2", "PySide6", ...]` trong spec.
- Không exclude `sammonny` khỏi bản Admin: `src.presentation.widgets/__init__` (và `src.application.*/__init__`)
  import dây chuyền tới SDK ⇒ exe crash "No module named 'sammonny'" khi khởi động.
- Exe windowed: `sys.stdout` là None (print của qfluentwidgets vô hại). Lỗi khởi động hiện trong hộp thoại
  "Unhandled exception in script" — đọc bằng UI Automation (PowerShell) khi không có console.
- App đóng gói: `main.ensure_portable_workdir()` chdir về thư mục exe (đường dẫn `data/`, `logs/`, `profiles/` tương đối).
- Onefile tạo 2 tiến trình (bootloader + app); cửa sổ thuộc tiến trình con.

## Bảng Fluent trong cửa sổ test
- `TableWidget` + header `ResizeToContents` ⇒ khi hủy cửa sổ, Qt gọi `sizeHint` vào `TableItemDelegate` đã bị xóa
  ⇒ access violation (ngẫu nhiên). Dùng `Interactive` + `setColumnWidth` cố định.

## Admin GUI
- `tools/license_issuer/admin_gui.py` dùng chung store/ledger với CLI `issuer.py`. Nút "Cấp key" bị khóa khi khóa ký
  không có trong `TRUSTED_PUBLIC_KEYS` của bản app (key cấp ra sẽ bị app từ chối).
- Hướng dẫn: `docs/04_guides/build_and_release.md`.
