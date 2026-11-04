# Instinct 009: Quản Lý Vòng Đời Trình Duyệt (Zero Zombies) & Dọn Dẹp Cache An Toàn

## 1. Bản Chất Kỹ Thuật (Technical Invariants)
- **Zombie/Orphan Browser Sweeping**:
  - Khi ứng dụng bị crash hoặc profile bị ngắt kết nối đột ngột, các tiến trình `chrome.exe` / `orbita.exe` có thể trở thành mồ côi (orphan processes) tiếp tục giữ lock file và ngốn tài nguyên RAM.
  - `BrowserProcessSupervisor.scan_orphan_browsers` quét toàn bộ hệ thống bằng cách rà soát `cmdline` trỏ tới thư mục profiles của ứng dụng nhưng không nằm trong danh sách active PIDs hoặc file `.process.lock`.
  - Quy trình tắt tiến trình sạch sẽ: `CDP Browser.close` -> `psutil Process Tree SIGTERM` -> `SIGKILL` -> `remove_lock`.
- **Dọn Dẹp Cache Mà Không Mất Phiên Đăng Nhập (Safe Cache Cleaning)**:
  - Các thư mục tốn dung lượng lớn gồm: `Default/Cache`, `Default/Code Cache`, `Default/GPUCache`, `Default/Service Worker/CacheStorage`, `ShaderCache`, `GrShaderCache`, và file tạm `*.tmp`, `*.crdownload`.
  - **Bảo Vệ Nghiêm Ngặt (PROTECTED_ITEMS)**: Tuyệt đối không xóa `Cookies`, `Preferences`, `Local State`, `Local Storage`, `IndexedDB`, `Extensions`, `Login Data` dưới bất kỳ trường hợp nào, đảm bảo 100% phiên đăng nhập TikTok và dữ liệu tài khoản được giữ nguyên vẹn.
- **Tối Ưu Working Set RAM**:
  - Gọi Win32 `EmptyWorkingSet` thu hồi các trang bộ nhớ vật lý unreferenced của toàn bộ cây tiến trình Chromium mà không ngắt socket mạng hay crash tab.

