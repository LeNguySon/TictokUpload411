# 015: Multi-Project Video Folders & Concurrent Batch Distribution

## 1. Context & User Requirement
Người dùng phản ánh hệ thống quản lý có nhiều dự án / nhiều nhóm (ví dụ: Nhóm Nhật, Nhóm Hàn, Nhóm Mỹ...), nhưng trước đó hộp thoại `BatchFolderUploadDialog` chỉ cho phép nạp 1 thư mục video của 1 nhóm đơn lẻ. Người dùng yêu cầu mở rộng để có thể nạp và phân bổ đồng thời cho nhiều dự án/nhóm cùng lúc.

## 2. Technical Solution & Architecture
1. **UploadService.distribute_multi_project_batches**:
   - Nhận danh sách các batches: `project_batches: list[dict[str, Any]]` chứa `project_id`, `project_name`, `folder_path`, và `profile_ids`.
   - Tính toán trước tổng số lượng video trên toàn bộ các nhóm để phát tín hiệu `progress(current, grand_total, msg)`.
   - Duyệt qua từng nhóm, quét đệ quy các file video hợp lệ, băm SHA-256 (4MB chunk) khử trùng lặp, chia đều (fair-share round-robin) cho các tài khoản đích của chính nhóm đó.
   - Video của Nhóm A chỉ phân bổ cho tài khoản Nhóm A, video của Nhóm B chỉ phân bổ cho tài khoản Nhóm B (ngăn chặn tuyệt đối việc nhầm lẫn giữa các chiến dịch).
2. **FolderDistributionWorker (Multi-Batch Mode)**:
   - Hỗ trợ cả 2 chế độ: single folder (backward-compatible) và `project_batches` (multi-project).
   - Chạy trên `QThreadPool`, phát tín hiệu `progress` gắn tên nhóm: `[Nhóm Japan] clip1.mp4`.
3. **BatchFolderUploadDialog Multi-Project UI**:
   - **Bảng 1 (Multi-Project Table)**:
     - Checkbox chọn từng nhóm (hoặc nút "Chọn Tất Cả Nhóm" / "Bỏ Chọn").
     - Tên Dự Án kèm badge.
     - Ô nhập đường dẫn video riêng của từng nhóm kèm nút "Chọn..." duyệt thư mục máy tính (tự động lưu vào CSDL `project_repo.update(video_folder=...)`).
     - Số lượng video hợp lệ quét được theo thời gian thực (`📁 45 video`).
     - Số lượng tài khoản LIVE của nhóm.
   - **Bảng 2 (Target Profiles Table)**:
     - Tự động đồng bộ và hiển thị tài khoản của tất cả các nhóm được chọn, có cột hiển thị rõ tên Dự Án.
   - **Zero GUI Freeze**: Chạy ngầm 100%, có thanh `ProgressBar` và nhãn hiển thị tiến trình mượt mà.

