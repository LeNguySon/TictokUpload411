# 014: Asynchronous Workers & Complete GUI Freeze Prevention Architecture

## 1. Context & User Requirement
Người dùng phản ánh hiện tượng khóa/treo/đơ giao diện (GUI Freeze / Not Responding) khi thao tác với các tác vụ I/O nặng và gửi ảnh chụp màn hình cận cảnh nút bấm `📁 Nạp Thư Mục Phân Bổ`.

## 2. Root Cause Analysis (RCA)
1. **Nạp Thư Mục Phân Bổ (`BatchFolderUploadDialog`)**: Quét đệ quy và tính hash SHA-256 (50MB - 1GB mỗi file) trực tiếp trên Qt Main Thread làm tê liệt UI từ 15-45 giây.
2. **Khởi chạy Orbita Antidetect (`_on_launch_orbita`)**: Gửi HTTP xoay IP proxy + TCP ping kiểm tra socket sống + khởi động tiến trình con chạy tuần tự trên Main Thread khiến màn hình bị khựng đơ.
3. **Thêm Video & Kéo thả (`_on_pick_video_files`, `_on_videos_dropped`)**: Vòng lặp `enqueue_video` tính hash trên Main Thread.
4. **Buffer I/O nhỏ**: Đọc chunk 1MB làm tăng số lượng Windows syscalls khi hash các video dung lượng lớn.
5. **Typo Nhãn Nút Bấm**: Nút bấm trên toolbar có dấu gạch dưới vô tình `Nạp Thư Mục _Phân Bổ` gây mất thẩm mỹ.

## 3. Technical Implementation
1. **FolderDistributionWorker (`QRunnable`)**:
   - Chạy băm SHA-256 và phân bổ video trong `QThreadPool`.
   - Bổ sung `ProgressBar` và nhãn trạng thái trực tiếp trên `BatchFolderUploadDialog` cập nhật theo thời gian thực: `🔍 Đang phân tích & kiểm tra trùng lặp: X/Y (filename)...`.
   - Hỗ trợ cơ chế hủy sớm `worker.cancel()`.
2. **OrbitaLaunchWorker (`QRunnable`)**:
   - Toàn bộ chu trình kiểm tra proxy, xoay IP, xác nhận daemon và khởi chạy Orbita qua GoLogin SDK/binary chạy trong luồng ngầm.
   - Báo cáo kết quả qua tín hiệu non-blocking `profile_launched` và `batch_completed`.
3. **VideoImportWorker (`QRunnable`)**:
   - Xử lý kéo thả hàng chục video hoặc chọn file từ Explorer không làm giật lag giao diện.
4. **Tăng Tốc Đọc File (4MB Buffer)**:
   - Nâng chunk buffer trong `UploadService.compute_sha256` từ 1MB lên 4MB, giảm 75% Windows I/O syscalls.
5. **Chuẩn Hóa Nhãn Giao Diện**:
   - Sửa toàn bộ `"Nạp Thư Mục _Phân Bổ"` thành `"Nạp Thư Mục Phân Bổ"` trên MainWindow, Dialog title, và các file unit test.
