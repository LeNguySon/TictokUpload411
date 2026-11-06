# Instinct 062: API chính thức: chia khối, đọc theo khối, tự làm mới token (SDK 1.8.3, 2026-11-07)

## Quy tắc TikTok (đã đối chiếu tài liệu, đừng đoán)
- FILE_UPLOAD: khối 5–64 MB; `total_chunk_count = size // chunk` (làm tròn XUỐNG), khối cuối gánh phần dư (≤ 128 MB);
  < 5 MB ⇒ 1 khối = cả video; 1–1000 khối; ≤ 4 GB; PUT lần lượt; 206 = tiếp, 201 = xong, 403 = upload_url hết hạn.
- OAuth: `POST https://open.tiktokapis.com/v2/oauth/token/` (form-urlencoded, grant_type=refresh_token).
  Refresh token XOAY VÒNG: phải lưu cái mới. Tài liệu ghi 2 bộ thời hạn khác nhau ⇒ luôn dùng `expires_in` trả về.

## SDK (`sdk/python/sammonny/platforms/tiktok.py`)
- `plan_direct_post_chunks(size)`; `init_direct_post` và `upload_video_chunks` dùng chung kế hoạch.
- `upload_video_chunks(video_path=...)` đọc từ đĩa theo khối (RAM ~ 1 khối; test dùng session tự viết vì MagicMock
  giữ mọi khối trong lịch sử gọi). `UploadUrlExpired` cho 403. MIME theo đuôi file.
- `refresh_access_token(...) -> TokenSet`; `TokenRefreshError(reconnect_required=...)`; không lộ secret trong lỗi.
- **Hybrid KHÔNG upload thật**: `execute_tos_upload` chỉ `time.sleep` khi URL chứa `tiktokcdn.com` (URL luôn là thế),
  và dựa vào ký request giả thiết bị — không phát triển phần đó. Chỉ API chính thức thật sự đăng được video.

## App
- `src/application/services/token_manager.py`: làm mới khi còn < 5 phút hoặc chưa rõ hạn (có refresh token);
  khóa theo hồ sơ; LƯU VAULT TRƯỚC khi dùng (`vault.save_oauth_payload`); invalid_grant ⇒ `ReconnectRequired` +
  `profiles.api_reconnect_required = 1` (tooltip cột Logged); 401 ⇒ làm mới 1 lần rồi thử lại; đi qua egress hồ sơ;
  thiếu client key/secret mà token chưa chắc hết hạn ⇒ vẫn dùng token.
- `refresh_token` dạng chữ thường trong CSDL (nhập hàng loạt) được chuyển vào Vault rồi xóa khỏi CSDL.
- "Cấu Hình API" lưu `client_key` đúng trường (bản cũ lưu vào `access_token`, vẫn đọc được).
- Sửa token trong hộp thoại hồ sơ GỘP vào payload cũ (trước: ghi đè làm mất refresh token).
- conftest `isolated_default_db`: repo không có db_path trỏ CSDL tạm (trước: `data/app.db` thật).
- E2E: `scratch/perf/e2e_official_upload.py` (server TikTok giả kiểm tra đúng quy tắc) ⇒ PASS.
