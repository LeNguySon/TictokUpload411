# Instinct 059: Phương pháp upload & Cài Đặt Upload (2026-11-06)

## SDK (sammonny 1.8.1 `platforms/tiktok.py`) — hành vi cần nhớ
- `validate_capability`: có token đã đăng ký ⇒ LUÔN dùng API chính thức (bỏ qua preferred_mode); kiểm tra API lỗi ⇒
  lặng lẽ chuyển sang trình duyệt. Token nằm lại trong `publisher._tokens` giữa các lượt upload.
- Direct Post và Studio DOM bỏ qua `schedule_time` (đăng ngay). DOM bỏ qua privacy/allow_*.
- Hybrid tự fallback sang DOM khi publish không thành công (kể cả http 0 = mất kết nối) ⇒ có thể đăng trùng.
- DOM chờ 1,2 s cho video xử lý + selector `:has-text` không hợp lệ trong querySelector ⇒ gần như luôn lỗi; khi không
  xác nhận được vẫn trả success với id `studio_post_<ts>` (`studio_<ts>` = đã thấy trang /content).

## App (đã xử lý phía app)
- `src/application/settings/upload_settings.py` (QSettings `upload/*`): method auto/official/hybrid/studio,
  allow_fallback (mặc định TẮT), studio_show_browser, reconcile_official. Dialog `upload_settings_dialog.py`,
  menu "Cài Đặt Upload"; `adapter.apply_settings()` khi mở app và khi lưu.
- Adapter: `_resolve_mode` tôn trọng lựa chọn (official thiếu token ⇒ `UploadMethodError`); official kiểm tra
  `query_creator_info` + privacy_level_options trước; mode khác ⇒ pop token khỏi `publisher._tokens`.
- Studio + (privacy ≠ PUBLIC hoặc có giờ hẹn) ⇒ từ chối trước khi gửi. DOM chỉ được chạy khi được phép: phiên
  `LazyActiveSession(dom_upload_allowed=False)` trả `_GuardedCdp` chặn `DOM.setFileInputFiles` (fallback ngầm của SDK
  dừng trước khi đăng). Ngữ cảnh mỗi lượt upload là thread-local (`_upload_scope`).
- `studio_post_*` ⇒ kết quả mơ hồ ("kiểm tra trên TikTok Studio"), không phải "đã đăng".
- Official thành công ⇒ `_reconcile_official` poll `publisher.reconcile` (5 s × 60) tới PUBLISH_COMPLETE/FAILED.
  Thuộc tính lớp; conftest `fast_upload_reconcile` đặt về 0 (nếu không test treo 5 phút).
- Lịch: `UploadService` hỏi `adapter.supports_native_schedule(profile)`; False + giờ hẹn tương lai ⇒
  `video_repo.defer_to_app_schedule` (về 'available', giữ giờ + hồ sơ) và trả `RemoteStatus.PENDING`; worker ghi
  "Chờ tới giờ đăng" (không phải lỗi). Bộ hẹn giờ của app đăng đúng giờ.
- Số dialog trong test thiết kế: 21.
