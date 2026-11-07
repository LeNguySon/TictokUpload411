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
