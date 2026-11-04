# 016: ProjectManagerDialog Refinement & Read-Only Table Protection

## 1. Context & User Requirement
Người dùng yêu cầu điều chỉnh hộp thoại Quản Lý Dự Án & Chiến Dịch (`ProjectManagerDialog`):
1. **Bỏ kho video ở dialog này**: Kho video đã được quản lý chuyên sâu và trực quan tại `BatchFolderUploadDialog`, không cần cấu hình dư thừa ở hộp thoại tạo/quản lý dự án.
2. **Không cho người dùng sửa dữ liệu trực tiếp khi click vào bảng**: Ngăn chặn tình trạng click nhầm kích hoạt inline cell editing trên bảng dự án.
3. **Thêm chức năng chỉnh sửa tên nhóm/dự án**: Cho phép người dùng đổi tên dự án thông qua nút bấm chuyên dụng hoặc double click vào hàng.

## 2. Technical Implementation
1. **Loại bỏ kho video**:
   - Xóa hàng nhập `Kho video:` (`self.folder_input` và `self.btn_browse`) khỏi biểu mẫu tạo dự án.
   - Xóa cột `Thư Mục Video` khỏi `self.table` (chuyển bảng thành 6 cột chuẩn: ID, Tên Dự Án, Tổng Profiles, Số Acc LIVE, Tổng Lượt View, Tổng $ Earned).
   - Nút `[ Tạo Dự Án ]` được đưa lên hàng 1 cạnh tên dự án và bảng chọn màu.
2. **Khóa chỉnh sửa trực tiếp khi click (NoEditTriggers)**:
   - `self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)`
   - Cờ của từng item đặt thành `Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable`, loại bỏ hoàn toàn `ItemIsEditable`.
3. **Chức năng Sửa Tên Dự Án**:
   - Thêm nút `[ ✏️ Sửa Tên Dự Án ]` (`self.btn_edit`) tại thanh công cụ dưới.
   - Hỗ trợ đổi tên bằng cách chọn hàng và bấm nút hoặc double-click vào hàng.
   - Mở `QInputDialog.getText` để người dùng nhập tên mới, gọi `project_repo.update(proj_id, name=new_name)` và làm mới bảng dữ liệu.

