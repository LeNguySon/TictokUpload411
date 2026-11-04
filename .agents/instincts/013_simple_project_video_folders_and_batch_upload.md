# 013: Simple Project-Specific Video Folders & Batch Distribution Sync

## 1. Context & User Requirement
Người dùng yêu cầu đơn giản hóa tối đa quy trình:
- Phân nhóm tài khoản theo Dự án (Project) tương ứng với việc phân nhóm nguồn video theo từng thư mục riêng của Dự án (ví dụ Nhóm Japan trỏ vào thư mục Japan, Nhóm Hàn trỏ vào thư mục Hàn).
- Nút bấm thanh công cụ: `📁 Nạp Thư Mục _Phân Bổ`.
- Khi bấm nút, mở `BatchFolderUploadDialog` với thư mục gốc được tự động nạp từ Dự án đang chọn, danh sách tài khoản tự động lọc theo Dự án.
- Thuật toán quét đệ quy (`rglob("*")`) tìm thấy toàn bộ video trong mọi thư mục con và phân bổ đều cho các kênh trong dự án.
- Khi người dùng đổi nhóm Dự án trên `project_combo`, cả hai bảng Hồ sơ và Bảng Video đồng thời lọc theo Dự án đó.

## 2. Technical Implementation
- `VideoRepository.list_available(project_id: int | None = None)`: Lọc video theo `assigned_profile_id IS NULL OR p.project_id = ?`.
- `MainWindow._on_project_changed()`: Gọi cả `self.refresh_profiles()` và `self.refresh_videos()`.
- `BatchFolderUploadDialog`: Nhận `initial_folder` và `project_id`, lọc `profile_repo.list_active(project_id=self.project_id)`.
- Nhãn nút toolbar: `"Nạp Thư Mục _Phân Bổ"`.
