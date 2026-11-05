# Build file exe & công cụ Admin cấp key

## 1. Build
```
python packaging/build_exe.py app     # -> dist/SonBetaPro/SonBetaPro.exe  (thư mục giao cho khách)
python packaging/build_exe.py admin   # -> dist/TAVM-Admin.exe             (CHỈ cho nhà phát triển)
python packaging/build_exe.py all
```
- Cần PyInstaller (`pip install pyinstaller`), mỗi bản mất khoảng 4–5 phút.
- `build/` và `dist/` đã nằm trong `.gitignore`.
- Spec: `packaging/tavm_app.spec` (one-folder), `packaging/tavm_admin.spec` (one-file).

## 2. Giao app cho khách
- Nén **cả thư mục** `dist/SonBetaPro/` (exe + `_internal/`) và gửi đi. Khách giải nén vào thư mục có quyền ghi
  (vd `D:\SonBetaPro`), **không** đặt trong `C:\Program Files` vì app ghi `data/`, `logs/`, `profiles/` cạnh exe.
- Bản exe không bao gồm `tools/` (công cụ cấp key) — có test kiểm tra spec.
- Trình duyệt Orbita / daemon SamMonny vẫn tìm theo `engine_paths` (biến môi trường `TAVM_ORBITA_PATH`,
  `TAVM_SAMMONNY_ROOT`, …), xem `development_setup.md` mục 2b.

## 3. Quy trình cấp key với TAVM-Admin.exe
1. Khách mở app → hộp thoại **Kích hoạt bản quyền** → bấm **Sao chép** mã máy → gửi cho bạn.
2. Mở `TAVM-Admin.exe` → nhập Khách hàng, chọn Gói, dán Mã máy, chọn số ngày → **Cấp key** → **Sao chép key**.
3. Khách dán key → **Kích hoạt**. Gia hạn / nâng cấp gói: cấp key mới, khách dán qua menu
   *Cài đặt → Bản quyền (Kích hoạt / Gia hạn)*.

- Khóa ký nằm ở `%LOCALAPPDATA%\TAVM-Issuer\signing_keys\` (DPAPI theo user Windows). Bấm **Sao lưu** ngay sau khi
  tạo, cất file `.pem` và mật khẩu ở 2 nơi khác nhau.
- Nếu Admin báo "Bản app hiện tại KHÔNG tin khóa …": thêm dòng được hiển thị vào
  `src/infrastructure/licensing/trusted_keys.py` rồi **build lại app** trước khi cấp key bằng khóa đó.
- Không bao giờ gửi `TAVM-Admin.exe` hay file `.pem` cho khách.
