# Bản Năng Kỹ Thuật: 005_context_menus_fluent_icons_and_table_state.md
**Ngày ghi nhận**: 04-11-2026  
**Chuyên đề**: Chuẩn hóa Menu Chuột Phải (Context Menu), Icon Vector Fluent Sắc Nét, và Quản Lý Trạng Thái Bảng QTableWidget

---

## 1. Vấn Đề Icon Sắc Nét: Emoji vs FluentIcon Vector
- **Hiện tượng**: Khi dùng Emoji Unicode trong Action string (ví dụ `"🌐 Mở Browser"`, `"🍪 Kiểm tra Cookie"`), trên Windows 11 ở các tỷ lệ Scale DPI khác nhau (100%, 125%, 150%), glyph emoji bị mờ, răng cưa hoặc màu sắc nhạt nhòa, không ăn khớp với Theme Light/Dark.
- **Giải pháp chuẩn**: Sử dụng thuần túy `Action(FluentIcon.<ICON_NAME>, "Tên thao tác", parent)` từ `qfluentwidgets`.
  - Icon được render từ SVG vector nguyên bản, sắc nét 100% tại mọi độ phân giải màn hình.
  - Tự động đổi màu tương phản (Light: `#201F1E`, Dark: `#FFFFFF`).

---

## 2. Lỗi Mất Đồng Bộ Khi Click Chuột Phải Trong QTableWidget
- **Hiện tượng**: Theo mặc định của Qt, khi người dùng click chuột phải vào một hàng chưa được chọn, Qt **không** tự động chọn hàng đó. Nếu hàng 0 đang được chọn mà chuột phải vào hàng 5, `self.selectedIndexes()` vẫn trỏ về hàng 0.
- **Giải pháp khắc phục**:
  ```python
  pos = event.pos()
  item = self.itemAt(pos)
  if item:
      clicked_row = item.row()
      selected_rows = {idx.row() for idx in self.selectedIndexes()}
      if clicked_row not in selected_rows:
          self.clearSelection()
          self.selectRow(clicked_row)
  ```

---

## 3. Tránh Trôi Dữ Liệu Khi Sắp Xếp Bảng (Row Index Drift)
- **Hiện tượng**: Khi bảng được sort theo một cột bất kỳ (ví dụ số views, ngày tạo), `row_index` không còn tương ứng với thứ tự trong danh sách CSDL ban đầu.
- **Giải pháp**:
  - Gắn dictionary dữ liệu trực tiếp vào Item tại Cột 0 qua `item.setData(Qt.ItemDataRole.UserRole, record)`.
  - Khi cần lấy dữ liệu, đọc từ `ItemDataRole.UserRole` thay vì dựa vào chỉ số dòng `row`.

---

## 4. Hỗ Trợ Multi-Selection Nhất Quán
- Toàn bộ tín hiệu (signals) từ Table Context Menu truyền `list[int]` thay vì đơn lẻ `int`.
- Giao diện tự động cập nhật nhãn động:
  - Nếu chọn 1 hàng: `Cập Nhật / Gán Proxy...`
  - Nếu chọn nhiều hàng: `Cập Nhật / Gán Proxy (5 hồ sơ)...`

