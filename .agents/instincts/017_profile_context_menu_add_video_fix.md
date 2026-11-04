# Instinct 017: Profile Context Menu Add Video Fix & Status Visibility

## 1. Ngữ Cảnh & Vấn Đề
Khi người dùng chuột phải vào một hàng hồ sơ trong bảng `ProfileTableWidget` và chọn `Nạp Video Vào Hàng Đợi Cho Hồ Sơ Này...`, video được chọn nhưng không xuất hiện trên bảng hàng đợi video (`VideoQueueTableWidget`), khiến người dùng tưởng chức năng menu chuột phải bị hỏng.

## 2. Nguyên Nhân Kỹ Thuật
1. **Lỗi Trạng Thái CSDL Bị Ẩn (`status = 'reserved'`)**:
   - Hàm `MainWindow._on_add_video_for_profiles` trước đây gọi:
     ```python
     vid_id = self.upload_service.enqueue_video(file_path=p, title=p.stem)
     self.video_repo.try_reserve(vid_id, target_profile_id)
     ```
   - `try_reserve` cập nhật `status = 'reserved'`.
   - Trong khi đó, `MainWindow.refresh_videos` truy vấn qua `video_repo.list_available()`, vốn chỉ lọc `WHERE v.status = 'available'`.
   - Kết quả: Video vừa nạp bị loại hoàn toàn khỏi truy vấn và không hiển thị trên bảng hàng đợi video.
2. **Nghẽn Luồng GUI (Main Thread Blocking)**:
   - Quá trình băm SHA-256 chạy trực tiếp trên luồng chính thay vì `QThreadPool`.
3. **Thiếu Hỗ Trợ Phân Bổ Khi Chọn Nhiều Hồ Sơ**:
   - Nếu bôi đen chọn nhiều hồ sơ, hàm cũ chỉ lấy `profile_ids[0]` và bỏ rơi các hồ sơ khác.

## 3. Quy Tắc & Giải Pháp Chuẩn
1. **Mở Rộng Truy Vấn CSDL Hàng Đợi Video**:
   - Trong `VideoRepository.list_available`:
     ```sql
     WHERE v.status IN ('available', 'reserved', 'uploading')
     ```
     Đảm bảo mọi video đang trong hàng đợi (dù đang sẵn sàng, được gán/giữ chỗ cho hồ sơ, hay đang tải lên) đều hiển thị trên bảng.
2. **Không Khóa Trạng Thái Sớm Khi Nạp**:
   - Video nạp vào hàng đợi được lưu với `assigned_profile_id` và trạng thái `'available'` để sẵn sàng lên lịch hoặc tải lên.
3. **Bất Đồng Bộ Tuyệt Đối Trên `QThreadPool`**:
   - Sử dụng `VideoImportWorker` cho mọi tác vụ nạp video qua menu chuột phải, phát tín hiệu thông báo tiến trình và cập nhật bảng khi hoàn tất.
4. **Hỗ Trợ Phân Bổ Đa Hồ Sơ (Fair-Share Round-Robin)**:
   - `VideoImportWorker` nhận `target_profile_ids: list[int]`. Nếu truyền nhiều hồ sơ, video được phân bổ đều xoay vòng cho từng hồ sơ.
   - Nhãn menu chuột phải tự động đổi theo ngữ cảnh:
     - 1 hồ sơ: `Nạp Video Vào Hàng Đợi Cho Hồ Sơ ({prof_name})...`
     - Nhiều hồ sơ: `Nạp Video Phân Bổ Cho ({count} hồ sơ)...`
