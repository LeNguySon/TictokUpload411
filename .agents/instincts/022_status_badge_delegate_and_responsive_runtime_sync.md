# Bản Năng Kỹ Thuật 022: Triệt Tiêu Lỗi Cắt Cụt 'stop...' Bằng StatusBadgeDelegate & Đồng Bộ Trạng Thái Profile Thực Tế

## 1. Bối Cảnh & Vấn Đề Gốc
- Trong giao diện bảng quản lý profile TikTok (`ProfileTableWidget`), cột số 12 ("Tình trạng") trước đây hiển thị chuỗi văn bản thuần túy `"stopped"`.
- Do giới hạn chiều rộng cột và padding của Fluent UI, Qt tự động thực hiện Text Elision (`...`) biến `"stopped"` thành `"stop..."` gây khó chịu và mất thẩm mỹ nghiêm trọng.
- Khi người dùng tương tác mở trình duyệt Orbita hoặc đóng cửa sổ trình duyệt (kể cả bấm dấu X trực tiếp trên cửa sổ Chrome/Orbita), trạng thái trên bảng không có phản hồi tức thời hoặc bị kẹt chuỗi `"stop..."`.

## 2. Giải Pháp Học Hỏi Từ Gloglin2609
- **`StatusBadgeDelegate` (QStyledItemDelegate)**:
  - Thay vì để QTableWidget vẽ text thuần, tạo delegate chuyên biệt vẽ huy hiệu dạng viên thuốc (**Pill Badge**) bằng `QPainter.drawRoundedRect` với bán kính bo tròn $12\text{px}$, chiều cao $24\text{px}$, căn giữa tuyệt đối ô bảng.
  - Tích hợp chấm đèn phát sáng (**Glowing Indicator Dot**) $3.5\text{px}$ và phông chữ Segoe UI DemiBold tương phản cao.
  - Phân loại màu sắc và Việt hóa ngữ nghĩa trực quan:
    - `"stopped"` / `"ready"` $\rightarrow$ **"Sẵn sàng"** (Huy hiệu xanh ngọc `#ECFDF5`, chấm xanh `#10B981`).
    - `"running"` $\rightarrow$ **"Đang mở"** (Huy hiệu xanh dương `#EFF6FF`, chấm xanh `#3B82F6`).
    - `"launching"` $\rightarrow$ **"Đang mở..."** (Huy hiệu vàng hổ phách `#FFFBEB`, chấm cam `#F59E0B`).
    - `"LIVE"` $\rightarrow$ **"LIVE"** (Huy hiệu xanh lá cây `#E6F9EE`, chấm xanh `#22C55E`).
    - `"DIE"` $\rightarrow$ **"DIE"** (Huy hiệu đỏ nhạt `#FEF2F2`, chấm đỏ `#EF4444`).
    - `"CHECKPOINT"` $\rightarrow$ **"CHECKPOINT"** (Huy hiệu cam `#FFF7ED`, chấm cam `#F97316`).
    - `"error"` $\rightarrow$ **"Lỗi"** (Huy hiệu đỏ `#FEF2F2`, chấm đỏ `#EF4444`).
  - Đặt độ rộng cố định cho cột 12 là $125\text{px}$ và trả về `sizeHint(125, 34)` để đảm bảo hiển thị hoàn mỹ trên mọi độ phân giải.

## 3. Quy Trình Đồng Bộ Hai Chiều Khi Mở và Đóng
1. **Khi bấm Mở Profile**:
   - UI lập tức đổi dòng tương ứng sang trạng thái `"launching"` (**"Đang mở..."**) để phản hồi thị giác trong vòng $0\text{ms}$.
   - Khi worker khởi chạy xong và phát hiện Debugger Port / PID $\rightarrow$ chuyển sang `"running"` (**"Đang mở"**).
   - Nếu khởi chạy lỗi $\rightarrow$ chuyển sang `"error"` (**"Lỗi"**).
2. **Khi Đóng Profile**:
   - Khi bấm "Đóng Profile": gọi `orbita_launcher.close_profile()` và cập nhật ngay dòng đó về `"LIVE"` (nếu có cookie/tài khoản) hoặc `"ready"` / `"stopped"`.
   - Khi người dùng bấm nút **X** tắt trình duyệt thủ công trên Windows: Bộ đếm thời gian `profile_status_timer` (chu kỳ $1500\text{ms}$) thăm dò socket debugger và danh sách tiến trình qua `is_profile_running()`. Ngay khi phát hiện port đóng, tự động cập nhật ô bảng về `"LIVE"` hoặc `"Sẵn sàng"` mà không cần reload toàn bộ bảng hay gây giật khung hình.

## 4. Quy Chuẩn Kỹ Thuật Bắt Buộc Cho Các Agent Kế Tiếp
- Không bao giờ gán text thô tiếng Anh (`"stopped"`, `"launching"`) vào ô trạng thái mà không thông qua `UserRole` và `StatusBadgeDelegate`.
- Luôn gọi `item.setData(Qt.ItemDataRole.UserRole, status)` khi cập nhật trạng thái trong `load_profiles` và `_update_profile_status_cell`.
- Giữ chu kỳ `profile_status_timer` ở mức $1500\text{ms}$ (1.5 giây), không tăng lên quá 3 giây để đảm bảo trải nghiệm người dùng liền mạch.
