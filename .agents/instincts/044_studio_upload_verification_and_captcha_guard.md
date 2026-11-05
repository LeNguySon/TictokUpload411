# Instinct 044: Studio Upload 4-Gate Verification & SecSDK Captcha Guard

## Bối Cảnh
Trong các hệ thống tự động hóa đăng video TikTok qua trình duyệt Web (Headless Studio Upload):
- Trước đây hàm `TikTokHeadlessStudioUploader.upload_via_studio` luôn mặc định trả về `success=True` kèm mã giả `publish_id=studio_post_<timestamp>` dù:
  1. Thẻ `<input type="file">` không tồn tại hoặc không đính kèm được video.
  2. Quá trình xử lý video trên web bị treo hoặc nút Post bị `disabled`.
  3. TikTok WAF kích hoạt SecSDK Captcha (Puzzle Slider / Rotate Image).
- **Hậu quả nghiêm trọng**:
  - **Thành công ảo (False Positives)**: Video chưa được đăng nhưng hệ thống đã chuyển file sang thư mục `_posted/` và đánh dấu `published` trong CSDL, gây lỡ lịch đăng hoặc đăng trùng.
  - **Khóa tài khoản (Permanent Ban)**: Hành vi gửi sự kiện click chuột mù mờ khi Captcha đang hiển thị là chỉ dấu 100% của bot tự động sơ sài, khiến AI ByteDance gắn cờ bot farm và ban tài khoản.

## Giải Pháp Kỹ Thuật (Kiến Trúc 4 Cổng Kiểm Soát 4-Gate Verification)

### 1. Gate 1 & Gate 3: Phòng Thủ SecSDK Captcha Tuyệt Đối
- Trước khi đính kèm file và sau khi gõ tiêu đề, kiểm tra `check_captcha_present()`.
- Nếu phát hiện Captcha:
  - **DỪNG NGAY LẬP TỨC**, tuyệt đối không click mù.
  - Trả về `UploadResult(success=False, status=RemoteStatus.MANUAL_REQUIRED, error="SecSDK Captcha challenge detected: upload suspended for account safety")`.
  - Giữ nguyên video trong hàng đợi để người dùng có thể mở trình duyệt giải tay an toàn.

### 2. Gate 2: Xác Thực File Input Node ID
- Nếu `file_node_id <= 0`:
  - Trả về ngay `UploadResult(success=False, status=RemoteStatus.FAILED, error="File input element not found in TikTok Studio DOM")`.
  - Không tiến hành gõ chữ hay bấm nút giả.

### 3. Gate 3: Kiểm Tra Trạng Thái Sẵn Sàng (Post Ready)
- Thăm dò trạng thái thuộc tính `disabled` hoặc class `disabled` của nút Post trong tối đa 3 giây.
- Nếu nút Post vẫn bị vô hiệu hóa (do web đang encode video hoặc lỗi định dạng):
  - Trả về `UploadResult(success=False, status=RemoteStatus.FAILED, error="Post button remained disabled or video processing incomplete")`.

### 4. Gate 4: Bằng Chứng Xác Nhận Xuất Bản Trên DOM (Authentic DOM Confirmation)
- Sau khi click Post với kỹ thuật Biometric Kinematics, lắng nghe phản hồi từ DOM trong tối đa 15 giây:
  - Kiểm tra URL chuyển hướng: `href.includes('/content')` hoặc `href.includes('/manage')`.
  - Kiểm tra Modal / Toast thành công: `bodyText.includes('uploaded')`, `Manage your posts`, `Your video has been`.
  - Bắt lỗi Toast từ chối: `.tiktok-toast-error`, `div[role="alert"]` (vi phạm tiêu chuẩn cộng đồng, vượt giới hạn đăng trong ngày).
- Nếu TikTok trả về Toast lỗi $\rightarrow$ Trả về `FAILED` kèm nội dung lỗi cụ thể từ máy chủ.
- Chỉ khi có bằng chứng xác nhận mới trả về `PUBLISH_COMPLETE`.

