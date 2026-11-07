# 065 — Giá trị mặc định / placeholder KHÔNG phải số đo (review 63877e2)

## Lỗi
- `profiles.optimal_hour` có `DEFAULT 12` và `calculate_optimal_post_hours([])` trả về placeholder `12:00` (`peak_users = 0`).
- Deep sync ghi placeholder đó vào CSDL như dữ liệu thật. Radar và hộp lên lịch thì tin cột trần `optimal_hour`.
- Hậu quả: 65/66 kênh hiện "Giờ vàng 12:00". Đây chính là lỗi người dùng đã báo trước đó, nay tái phát.

## Quy tắc
- Chỉ dùng `measured_optimal_schedule(profile)` trong `src/domain/analytics/optimal_hours.py`.
  - Nó chỉ trả kết quả khi `optimal_posting_hours_json` có `peak_users > 0`. Không đọc cột trần `optimal_hour`.
- Mọi nơi ghi giờ hoạt động (sniffer, deep sync) phải ghi kèm `optimal_posting_hours_json` có `peak_users`.
- Hàm parser có giá trị fallback để "UI không trống" thì nơi lưu phải lọc fallback đó ra.
  - Không có dữ liệu thì để NULL, và UI tự rơi về số liệu tính từ video của chính kênh.

## Kèm theo
- Chữ lấy từ TikTok (tiêu đề video, tên kênh đối thủ, quốc gia…) hiển thị trong `QLabel` rich-text phải qua `html.escape`.
- Số từ API có thể là chuỗi: dùng `_count()`, đừng format `:,` trực tiếp.
- Dependency bắt buộc (`keyring`) không được bọc `try/except ImportError → None`.
  - Vault sẽ im lặng không lưu token, và mypy đỏ CI.

## Timer khởi động phải thuộc về cửa sổ (CI crash access violation)
- `QTimer.singleShot(ms, lambda: self...)` trong `__init__` của MainWindow không chết theo cửa sổ.
  - Trong suite, các timer này nổ 119 lần bên trong các test SAU: 78 lần prewarm 9 dialog cho cửa sổ đã đóng, trên CSDL tạm đã bị xoá.
  - Hậu quả: SQLite chạy trên GUI thread giữa các test khác (test flaky) và CI crash access violation.
- Dùng `self._defer(ms, slot)`: tạo `QTimer(self)` single-shot, `closeEvent` gọi `_stop_deferred_jobs()`. Prewarm giãn cách theo hàng đợi (`_prewarm_next`), không bắn 9 singleShot cùng lúc.
- Cách bắt lỗi kiểu này: plugin pytest ghi lại "job nổ trong test nào / cửa sổ được tạo ở test nào". Hai giá trị phải luôn trùng nhau.

## "Không biết" khác với "Tắt" (review 1228668 + telemetry)
- Khi `fetch_publish_settings` thất bại (lỗi mạng, HTTP 403, hoặc TikTok trả `status_code` khác 0 trong HTTP 200), code cũ vẫn lưu cả 3 cờ là `False`, tức là báo sai "kiểm tra bản quyền đang TẮT".
  - Khi thất bại phải trả `{}`, và nơi gọi không lưu gì.
- Đừng gán `widget.mousePressEvent = fn`: mypy báo `method-assign` và CI đỏ. Dùng `ClickableLabel` (signal `clicked`) trong `src/presentation/widgets/clickable_label.py`.
- Số liệu thay đổi chậm (phân tích sâu theo video, 2 request/video) phải có cửa sổ làm mới: `DEEP_VIDEO_REFRESH_HOURS = 6`.
  - Video chưa có dữ liệu cũng được ghi lại lần thử, để không bị hỏi lại ở mỗi lần sync.

## Kiểm chứng trên tài khoản thật @swall.pain (2026-11-07)
- Chỉ test giả lập (mock) thì không bắt được các lỗi dưới đây. Mỗi lần sửa phần thu thập dữ liệu, hãy chạy probe thật trên profile 78 để đếm request và đo thời gian.
- `getHashCount`: gọi `POST {}` thì không có phản hồi (treo 10 giây × 2 lần mỗi lần sync). Phải dùng `GET`; dữ liệu nằm dưới `CountData.<uid>` → dùng `hash_count_data()`.
- `video_finish_rate_realtime` luôn trả `null`. Tỷ lệ xem hết = điểm cuối của đường cong `video_retention_rate_realtime`.
- `getPenaltyDetails.penalties[0].date` là NGÀY XỬ PHẠT. TikTok không gửi hạn chót kháng cáo, nên đừng gọi cột này là "hạn".
- Trạng thái thật của TikTok là `can_appeal` / `under_review` / `penalized`. Phải dịch hết qua `violation_status_text()`.
- Ô chọn ngày giờ phải đặt `setDisplayFormat("dd/MM/yyyy HH:mm")`. Locale Mỹ hiển thị 08/11 thành "11/8", người dùng đọc nhầm sang tháng 8.
- Cửa sổ làm mới dữ liệu: chọn top N TRƯỚC rồi mới lọc bản còn mới. Lọc trước rồi `LIMIT` thì vòng lặp sẽ trượt xuống N video cũ tiếp theo ở mỗi lần sync.
- Kết quả: mỗi lần sync giảm từ 18 → 8 request và từ 21 → 5,5 giây.
