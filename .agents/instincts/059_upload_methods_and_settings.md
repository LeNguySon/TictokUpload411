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

## SDK đã vá tại nguồn (sdk/python/sammonny/platforms/tiktok.py, 2026-11-06 tối)
- Agent khác đã sửa phần lớn lúc 18:45 (không fallback hybrid→DOM, không id giả, chờ nút Đăng 60 s, Direct Post từ
  chối giờ hẹn, kiểm tra privacy). Bản vá bổ sung: chọn phương pháp tôn trọng preferred_mode kể cả khi có token;
  API lỗi KHÔNG tự chuyển (tham số `allow_fallback`, mặc định tắt); upload() không đi tiếp khi capability
  unauthorized; hybrid 4xx/mã API ≠ 0 = FAILED (thử lại được), timeout/5xx = mơ hồ; Studio: privacy/quyền tương tác
  phải được xác nhận (không thì FAILED, không đăng), giờ hẹn bị từ chối trước khi mở trang, chờ xử lý/xác nhận cấu
  hình được (PROCESSING_TIMEOUT_SEC 600, CONFIRM_TIMEOUT_SEC 30). Test: sdk `tests/test_tiktok_upload_safety.py`.
- `sdk/python` KHÔNG nằm trong git của repo SDK (untracked); app cài SDK từ `vendor/*.whl` (site-packages). Bản gốc
  trước vá: `scratch/sdk_backup/tiktok.py.orig`. Test TAVM với mã nguồn SDK: `PYTHONPATH=<repo>/sdk/python pytest`.
- conftest `fast_studio_waits`: rút ngắn chờ Studio trong test (trước đó một test chiếm 60 s).
- Đã đóng gói & cài SDK 1.8.2 (wheel `vendor/sammonny-1.8.2-py3-none-any.whl`, `pip install --user --no-deps
  --force-reinstall`); chỉ khác 1.8.1 ở `__init__.py` + `platforms/tiktok.py`. Ghim `sammonny==1.8.2` trong
  pyproject.toml / requirements.txt. `.venv` cài editable (trỏ mã nguồn) nên đã có code mới; exe trong `dist/` cần build lại.
- Lỗi chập chờn có sẵn (không do SDK): cả bộ test thỉnh thoảng sập "Windows fatal exception: access violation" trong
  `test_video_appeal_and_creator_reapply.py`; nghi `AccountHealthDialog` (ThreadPoolExecutor + QTimer poll) trong test
  không có qtbot. Chạy riêng file luôn pass.

## Định tuyến sau khi xác nhận Hybrid không upload thật (2026-11-07)
- `COOKIE_HYBRID_AVAILABLE = False` (sammonny_adapter): chọn Hybrid ⇒ `UploadMethodError` rõ ràng; nhãn cài đặt ghi
  "chưa hoạt động". Chỉ bật lại khi SDK truyền video thật.
- Tự động: có token ⇒ API chính thức; không token ⇒ Studio DOM nếu video công khai & không hẹn giờ, ngược lại báo
  "chưa kết nối TikTok API". `supports_native_schedule` luôn False ⇒ app tự giữ & đăng đúng giờ.
- Tự chuyển khi API lỗi ⇒ Studio (chỉ khi video hợp lệ cho DOM), không còn chuyển sang Hybrid.
