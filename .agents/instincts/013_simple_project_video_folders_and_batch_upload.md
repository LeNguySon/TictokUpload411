# 013: Simple Project-Specific Video Folders & Batch Distribution Sync

## 1. Context & User Requirement
Người dùng yêu cầu đơn giản hóa tối đa quy trình và cập nhật phía Giao diện:
- Phân nhóm tài khoản theo Dự án (Project) tương ứng với việc phân nhóm nguồn video theo từng thư mục riêng của Dự án (ví dụ Nhóm Japan trỏ vào thư mục Japan, Nhóm Hàn trỏ vào thư mục Hàn).
- Nút bấm thanh công cụ: `📁 Nạp Thư Mục _Phân Bổ`.
- Checkbox `Lên lịch TikTok Studio (Cloud)` trực tiếp trên thanh công cụ Video ở màn hình chính, đồng bộ tự động vào `ScheduleVideoDialog`.
- Bảng Video (`VideoQueueTableWidget`): Bổ sung cột hiển thị `Dự Án` rõ ràng (ở vị trí cột 2, ngay sau cột `Tiêu đề`) để người dùng nhận diện ngay video thuộc chiến dịch nào.
- Hộp thoại Nạp Thư Mục Phân Bổ (`BatchFolderUploadDialog`):
  - Hiển thị Banner Dự án mục tiêu ở đầu dialog (`🏷️ Chiến Dịch / Dự Án Mục Tiêu: [Tên Dự Án]`).
  - Tự động duyệt đệ quy `rglob("*")` và hiển thị nhãn số lượng video tìm thấy theo thời gian thực khi chọn đường dẫn.
  - Tự động lọc chỉ hiển thị các tài khoản của Dự án đó.

## 2. Technical Implementation
- `table_helpers.get_video_table_headers()`: 15 cột, chèn cột `Dự Án` tại index 2.
- `VideoRepository.list_available()`: `LEFT JOIN projects pr ON p.project_id = pr.id` và lấy trường `pr.name AS project_name`.
- `VideoQueueTableWidget.load_videos()`: Render cột `Dự Án` từ `v.get("project_name")` hoặc tên thư mục nguồn gốc `Path(v["file_path"]).parent.name`.
- `MainWindow`: Thêm `self.chk_toolbar_studio_schedule` trên thanh công cụ Video.
- `BatchFolderUploadDialog`: Thêm banner `lbl_project_badge`, tự động đếm file `_update_scanned_files_count`, nhận `project_name`.
