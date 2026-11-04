# Hướng Dẫn Cài Đặt Môi Trường Phát Triển (Development Setup Guide)

Tài liệu này hướng dẫn chi tiết cách thiết lập môi trường lập trình, cài đặt các công cụ kiểm soát chất lượng và chạy ứng dụng trên máy trạm Windows.

---

## 1. Yêu Cầu Hệ Thống & Tiền Đề

- **Hệ điều hành**: Windows 10 (bản 20H2 trở lên) hoặc Windows 11 64-bit.
- **Python**: Phiên bản **Python 3.11.x** hoặc **Python 3.12.x** (khuyến nghị tải từ [python.org](https://www.python.org/downloads/windows/) và tích chọn "Add python.exe to PATH").
- **Git**: Phiên bản mới nhất.
- **PowerShell**: Phiên bản 5.1 hoặc PowerShell 7+.

---

## 2. Các Bước Cài Đặt Môi Trường Ảo

Mở **PowerShell** và di chuyển vào thư mục dự án:

```powershell
# 1. Điều hướng vào thư mục dự án
cd D:\TictokUpload411

# 2. Khởi tạo môi trường ảo Python chuyên biệt
python -m venv .venv

# 3. Kích hoạt môi trường ảo
# Nếu gặp lỗi Execution Policy, chạy lệnh: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1

# 4. Nâng cấp pip lên phiên bản mới nhất
python -m pip install --upgrade pip

# 5. Cài đặt toàn bộ dependencies sản xuất và phát triển
pip install -r requirements.txt
```

---

## 3. Khởi Tạo Cơ Sở Dữ Liệu Ban Đầu

Ứng dụng yêu cầu khởi tạo CSDL SQLite từ bộ migration:

```powershell
# Chạy script migration để tạo 24 bảng dữ liệu
python -m infrastructure.database.migrations.migration_runner --db-path ./data/app.db
```

Sau khi chạy xong, file CSDL `./data/app.db` sẽ được tạo kèm đầy đủ 24 bảng và ràng buộc khóa ngoại được kích hoạt.

---

## 4. Chạy Ứng Dụng Ở Chế Độ Phát Triển

```powershell
# Khởi chạy ứng dụng
python -m app.main
```

---

## 5. Các Lệnh Kiểm Tra Chất Lượng Mã Nguồn Thường Dùng

```powershell
# 1. Kiểm tra lỗi cú pháp và style với Ruff
ruff check .

# 2. Tự động sửa các lỗi format đơn giản
ruff check --fix .

# 3. Kiểm tra kiểu dữ liệu nghiêm ngặt với Mypy
mypy --strict app/ application/ domain/ infrastructure/

# 4. Chạy toàn bộ bộ test tự động
pytest -v

# 5. Chạy test kèm báo cáo độ bao phủ mã nguồn (Coverage)
pytest --cov=app --cov=application --cov=domain --cov=infrastructure --cov-report=term-missing
```

