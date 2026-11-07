# 066 - Collapsible Video Panel Docking & User Geometry State

## Bối cảnh & Vấn đề
Trong ứng dụng Desktop đa bảng (Dual-Table Splitter) như `TikTokManagerMainWindow`:
Bảng Profile ở trên chiếm 55%, bảng Video ở dưới chiếm 45%. Khi người dùng quản lý hàng trăm tài khoản TikTok, việc bảng Video chiếm cố định ~340px khiến vùng xem profile bị thu hẹp đáng kể.

Nếu dùng `QSplitter` thuần túy:
1. Khi kéo splitter xuống đáy, container dưới có thể bị ép về 0px (mất luôn thanh công cụ/tiêu đề và người dùng không có cách nào click để mở lại).
2. Khi mở lại, splitter không nhớ kích thước trước đó mà người dùng đã tùy chỉnh.
3. Người dùng thiếu nút bấm trực quan (1-click toggle) và phím tắt tiện lợi.

## Giải pháp Kiến trúc Chuẩn
1. **Docking Bar Pattern**:
   - Khi thu gọn (`_collapse_video_panel`): Ẩn bảng dữ liệu `self.video_table.setVisible(False)`, nhưng giữ nguyên thanh công cụ `self.bottom_toolbar` ở đáy (~42px) đóng vai trò dock bar.
   - Gọi `self.splitter.setCollapsible(1, False)` để ngăn việc kéo splitter làm mất thanh dock đáy.
2. **Multi-Trigger Interaction**:
   - Nút công cụ `self.btn_toggle_video`: Vector icon `FluentIcon.DOWN` khi mở, `FluentIcon.UP` khi thu gọn.
   - Nhấp vào tiêu đề `self.lbl_video_header`: Đặt `PointingHandCursor`, click chuột trái gọi toggle.
   - Phím tắt toàn cục `Ctrl+B` qua `QShortcut(QKeySequence("Ctrl+B"), self)`.
3. **Geometry Memory**:
   - Lưu lại `self._saved_video_splitter_height` trước khi thu gọn (tối thiểu 200px, mặc định 340px) để khi mở lại (`_expand_video_panel`), bảng trở về đúng kích thước mong muốn.
4. **Auto-Expand on Data Ingestion**:
   - Khi đang thu gọn, nếu người dùng kích hoạt các hành động nạp/tải dữ liệu (`_on_pick_video_files`, `_on_open_batch_folder_upload`, `_on_start_upload_queue`), tự động mở lại bảng video để người dùng quan sát tiến trình.
