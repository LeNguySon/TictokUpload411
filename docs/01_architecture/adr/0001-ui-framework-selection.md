# ADR-0001: Lựa Chọn UI Framework — PyQt6 & PyQt-Fluent-Widgets

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-11-04
- **Người phê duyệt:** Lead Software Architect
- **Phạm vi:** Presentation Layer

---

### Bối Cảnh & Vấn Đề (Context)
Ứng dụng cần quản lý hàng nghìn tài khoản TikTok và hàng trăm tệp video trong hàng đợi tải lên. Bảng hiển thị yêu cầu khả năng lọc, sắp xếp, tìm kiếm tức thì, vẽ các thanh tiến độ (ProgressBar) nội tuyến và cập nhật liên tục từ các tiến trình mạng chạy nền. Ứng dụng phải hoạt động mượt mà trên hệ điều hành Windows 10 và 11.

Các phương án được cân nhắc:
1. **Electron.js / Webview2**: Phát triển UI nhanh với React/Vue, nhưng tiêu tốn RAM lớn (thường > 500MB), khởi động chậm, và việc tích hợp các thư viện Python chuyên sâu (như DPAPI, SQLite driver, video hasher) qua IPC phức tạp.
2. **Tkinter / CustomTkinter**: Nhẹ nhưng thiếu hỗ trợ ảo hóa bảng dữ liệu lớn (Virtualization), thiếu hệ thống điều khiển Fluent hiện đại của Windows 11, xử lý đa luồng dễ gây crash.
3. **PyQt6 + PyQt-Fluent-Widgets**: Native C++ binding thông qua Python, tiêu tốn RAM rất thấp (khoảng 80MB - 150MB), hỗ trợ kiến trúc Model/View (`QAbstractTableModel`) xử lý mượt mà hàng chục nghìn dòng, tích hợp sẵn Fluent Design System 2.0 (Mica/Acrylic effect, InfoBadge, StateToolTip).

---

### Quyết Định (Decision)
Lựa chọn **PyQt6 kết hợp với PyQt-Fluent-Widgets**.

---

### Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực**:
  - Giao diện đồng nhất 100% với phong cách Fluent Design của Windows 11.
  - Hiệu năng cuộn bảng đạt 60 FPS nhờ cơ chế View Virtualization của Qt Model/View.
  - Sử dụng chung ngôn ngữ Python 3.11 với tầng logic nghiệp vụ, không cần cầu nối IPC.
- **Tiêu cực / Rủi ro**:
  - Đòi hỏi các lập trình viên phải nắm vững kiến trúc Qt Event Loop và cơ chế Signal/Slot.
  - Phải tuân thủ nghiêm ngặt quy tắc không tương tác widget từ thread con.

