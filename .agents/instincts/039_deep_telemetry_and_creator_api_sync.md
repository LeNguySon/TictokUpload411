# Instinct 039: 4-Tier Deep Telemetry Engine & Creator API Sync

## Bối Cảnh
Trước đây, module thu thập dữ liệu TikTok chỉ dừng lại ở việc đọc 4 số liệu công khai qua DOM Hydration (`followers`, `following`, `likes`, `videos_count`). Điều này để lại nhiều hạn chế lớn cho người dùng MMO/Creator:
1. **Thiếu số liệu Creator Center**: Không thu thập được doanh thu (`money_earned`), chỉ số RPM (`rpm`), số dư khả dụng (`balance`), và tình trạng KYC tài khoản.
2. **Không có chi tiết video & Lượt xem 30 ngày (`views_month`)**: Không có danh sách video trong `videoTables`, không tính được hiệu suất view trong 30 ngày gần nhất (chỉ số quyết định thuật toán đề xuất của TikTok).
3. **Mù thông tin cảnh cáo/gậy vi phạm (`violateVideos`)**: Không phát hiện được video bị bóp tương tác, đánh bản quyền hoặc kênh bị dính strike vi phạm tiêu chuẩn cộng đồng.
4. **Sniffer bị ngắt kết nối**: `TikTokNetworkSniffer` đã có sẵn parser chuẩn cho 5 endpoint TikTok nhưng chỉ lắng nghe thụ động qua CDP khi mở trình duyệt, không được kích hoạt trong tác vụ sync nền.

## Giải Pháp Kỹ Thuật (Industrial Deep Telemetry)
1. **Kiến Trúc Thu Thập Đa Tầng (4-Tier Architecture)**:
   - **Tầng 1 (Offline Cookie Analysis)**: Kiểm tra trạng thái LIVE/DIE, cookie `sessionid`, thời hạn hiệu lực từ SQLite mà không cần tốn tài nguyên mạng.
   - **Tầng 2 (Authenticated Creator Center APIs)**: Khi profile có cookie hợp lệ, sử dụng `GoLoginTikTokClient.request_api()` với fingerprint Chrome 120 TLS JA3 và proxy cố định của profile để gọi 4 endpoint Creator:
     - `/api/user/detail/?uniqueId=...`: Lấy SecUID, Avatar URL, Follower/Like chuẩn xác.
     - `/api/creator/item/list/?count=20`: Đồng bộ video vào `videoTables`, phân loại view 30 ngày vào `views_month` và lưu `statisticTable`.
     - `/api/creator/dashboard/overview/`: Cập nhật `rpm`, `money_earned`, `balance`.
     - `/api/creator/violation/`: Cập nhật cảnh cáo và video vi phạm vào `violateVideos`.
   - **Tầng 3 (Public DOM Hydration Fallback)**: Nếu profile chưa đăng nhập (không có cookie) hoặc Creator API bị từ chối, tự động thoái lui sang phân tích DOM công khai qua proxy để lấy số liệu cơ bản.
   - **Tầng 4 (Local Avatar Caching)**: Tải ảnh đại diện về bộ nhớ đệm cục bộ (`storage_dir/avatar.jpg`), cập nhật vào CSDL để hiển thị tròn mượt mà trên UI (`CircularAvatarDelegate`).

2. **Khả Năng Phục Hồi Lỗi Từng Phần (Fault-Tolerant Degradation)**:
   - Mỗi lệnh gọi Creator API được bọc trong một khối `try...except` độc lập.
   - Nếu TikTok chặn 1 endpoint (ví dụ: HTTP 403 ở Dashboard Overview do chưa bật tính năng kiếm tiền), các endpoint còn lại (User Detail, Video List, Violation) vẫn tiếp tục được xử lý bình thường mà không làm gãy quy trình đồng bộ.

3. **Tính Toán Cửa Sổ 30 Ngày Chuẩn Xác**:
   - `views_month` được tổng hợp dựa trên điều kiện `item.create_time >= now - 30 * 86400`.
   - Lưu trữ tách biệt với `total_views` lũy kế toàn kênh trong `statisticTable` và `profiles`.

