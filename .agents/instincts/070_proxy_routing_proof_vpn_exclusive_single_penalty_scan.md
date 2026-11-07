# 070 — Proxy/VPN: chứng minh định tuyến thật, proxy ⊕ VPN, quét vi phạm 1 lần

Đã kiểm chứng ngày 2026-11-07 trên bản sao CSDL thật, với profile 78 (@swall.pain).

## Cách chứng minh "request đi qua đúng proxy của profile" (đáng dùng lại)
- Dựng `D:\tavm_probe\logging_proxy.py`: một proxy HTTP CONNECT trong cùng tiến trình, ghi lại từng host đích và header `Proxy-Authorization`.
- Dựng 2 proxy A và B. Gán A → chạy các chức năng thật → gán sang B → chạy lại. Đếm số request ở mỗi proxy.
- Kết quả:
  - 264/264 request đi qua A (gồm cả avatar tải từ CDN), và đều có `Proxy-Authorization`.
  - Sau khi gán lại sang B: 264/264 đi qua B, A còn 0.
- Proxy chết: curl báo "Failed to connect ... over proxy 127.0.0.1", tức không rơi về kết nối trực tiếp.
- Không có proxy và không bật direct: `EgressBlocked` chặn ngay trước khi gửi.

## Lỗi đã sửa
- **Quét vi phạm 2 lần mỗi lần sync** và mỗi lần bấm "Quét Toàn Kênh":
  - `fetch_account_standing` tự quét, rồi nơi gọi lại quét thêm. 162/177 request của một lần sync là `getPenaltyDetails`.
  - Cách sửa: quét `fetch_video_violations` trước, rồi truyền kết quả vào `fetch_account_standing(..., violations=...)`. Kết quả: 177 → 94 request, 23,6 → 16,0 giây.
- **Profile có cả proxy lẫn VPN:** bảng hiện "WireGuard VPN", nhưng trình duyệt và API thực ra dùng proxy.
  - Cách sửa: `_exclusive_egress` trong `ProfileRepository`. Gán proxy thì xoá VPN, gán VPN thì xoá proxy.
  - Migration giữ proxy, vì đó là thứ trình duyệt thực sự dùng.
- **Proxy dùng chung không có cảnh báo:**
  - Combo gán proxy giờ hiện "N hồ sơ đang dùng".
  - Khi một proxy kết thúc với nhiều hơn 1 hồ sơ, `shared_proxy_warning` hiện cảnh báo trên cửa sổ chính.

## Quy tắc
- Mọi client HTTP gửi tới TikTok thay mặt một profile đều phải đi qua `resolve_profile_egress`. Không được tự tạo `requests` hay `urllib` không có proxy.
- Khi đếm request, phải đếm ở proxy (hoặc patch ở mức lớp `GoLoginTikTokClient.request_api`). Bọc một instance client chỉ đếm được một phần: moderation dùng client riêng.
- CSDL thật lúc kiểm tra có 53 profile chia nhau 2 proxy (27 + 26), cả hai đều `dead`. Đây là việc của người dùng: thay proxy sống và dùng mỗi profile một proxy.
