# Instinct 029 — Inline Table Multi-Threaded Video Upload Progress & Error Display
## Ngày ghi nhận: 2026-11-05

## Bối cảnh kỹ thuật
- Trong các ứng dụng desktop MMO tự động hóa upload video đa luồng, việc tách riêng một bảng console nhật ký ở dưới chân trang có thể chiếm dụng nhiều diện tích chiều cao màn hình, làm giảm số lượng hàng video mà người dùng có thể quan sát được trên bảng chính.
- Người dùng có nhu cầu theo dõi tiến độ và phát hiện lỗi tức thì ngay tại từng hàng video tương ứng.

## Nguyên nhân gốc rễ & Thách thức
1. **Chia cắt ngữ cảnh quan sát (Fragmented Context)**: Khi console log nằm tách biệt ở dưới, người dùng phải chuyển mắt qua lại giữa dòng video trên bảng và dòng log dưới console để đối chiếu trạng thái.
2. **Chiếm dụng không gian hiển thị (Screen Real Estate Starvation)**: Splitter chứa widget console khiến bảng video bị thu hẹp chiều cao, giảm tầm nhìn danh sách hàng đợi video.
3. **Hiển thị lỗi tức thời (Immediate Visual Defect Feedback)**: Khi một video bị lỗi (timeout, proxy chết, sai định dạng, checkpoint), người dùng cần thấy ngay thông báo lỗi nổi bật màu đỏ tại cột của video đó mà không cần đào bới trong console.

## Giải pháp kiến trúc chuẩn
1. **Thiết Kế Cột Trực Quan Trong Bảng Video (`VideoQueueTableWidget`)**:
   - Cột 10: `"Tiến trình"` chứa `ProgressBar` và phần trăm % rõ ràng.
   - Cột 11: `"Nhật Ký Upload"` hiển thị trực tiếp dòng log hiện tại của video đó (`[START]`, `[CHUNK 45%]`, `[PUBLISH]`, `[SUCCESS]`).
   - Khi có lỗi: Cột 11 lập tức hiển thị màu đỏ `#D83B01` với tiền tố `❌ Lỗi: {error_message}`, đồng thời lưu toàn bộ lịch sử vết lỗi trong Tooltip để rê chuột xem ngay.
2. **Cập Nhật Cục Bộ Theo Hàng (`Row-Targeted Delta Updates`)**:
   - Hàm `append_log(video_id, ...)` và `set_video_error(video_id, ...)` tìm chính xác hàng qua `find_row_by_video_id` và chỉ cập nhật cell tương ứng, không refresh toàn bảng, giữ giao diện mượt mà 60 FPS.
3. **Loại Bỏ Console Rời Ở Dưới**:
   - Trả lại 100% không gian hiển thị cho `self.video_table` trong `bottom_container`, loại bỏ splitter dọc và nút ẩn hiện console.

