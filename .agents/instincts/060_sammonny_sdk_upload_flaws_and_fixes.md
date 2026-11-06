# Instinct 060: SamMonny SDK TikTok Upload Pipeline Flaws & Upstream Fixes

## 1. Bối cảnh & Nguyên Nhân Gốc Rễ (Context & Root Causes)
Trong `sammonny/platforms/tiktok.py` (cả repo nguồn `D:\SamMonnygocLiengXiPoker` và `site-packages`), tồn tại 9 khiếm khuyết trong luồng xuất bản video:
1. **Lên lịch Direct Post v2**: API `/v2/post/publish/video/init/` không có tham số `schedule_time`. SDK gửi nhưng TikTok đăng ngay lập tức. Giải pháp: Từ chối gọi API Direct Post khi có `schedule_time`, yêu cầu Local Scheduling hoặc Studio DOM.
2. **DOM bỏ qua privacy & schedule**: `upload_via_studio` chỉ gắn file và gõ caption, không chọn radio privacy hoặc toggle schedule. Giải pháp: Thêm DOM evaluate script click radio `Public/Friends/Only you` và toggle hẹn giờ.
3. **ID giả `studio_post_...`**: Khi không thấy thẻ xác nhận, SDK bịa ID giả `studio_post_{timestamp}` và trả về `success=True`. Giải pháp: Tuyệt đối không sinh ID giả, trả về `success=False`, `RemoteStatus.UNKNOWN`, `is_ambiguous=True`.
4. **Đăng trùng Hybrid Fallback**: Khi Phase 3 (V8 in-browser fetch) timeout/lỗi, SDK tự gọi `upload_via_studio`. Nếu request V8 trước đó đã tới server TikTok, việc upload lại bằng DOM làm video bị đăng 2 lần. Giải pháp: Dừng lại và báo `is_ambiguous=True`, không tự ý gọi DOM.
5. **Selector lỗi cú pháp & timeout 1.2s**: `button:has-text("Post")` là cú pháp Playwright không hợp lệ trong native DOM querySelector (ném SyntaxError); timeout chờ transcode chỉ có 1.2s (6 * 0.2s). Giải pháp: Dùng JavaScript tìm duyệt mảng button theo text và nâng timeout lên 60s.
6. **Nuốt lỗi API trong `validate_capability`**: Khi `query_creator_info` lỗi, SDK nuốt lỗi rồi âm thầm trả về `HEADLESS_STUDIO`. Giải pháp: Giữ nguyên lỗi gốc trong `CapabilityResult.error` và không tự chuyển mode nếu mode OFFICIAL được yêu cầu.
7. **Thiếu đối soát trạng thái bài đăng**: SDK trả về `success=True` dạng fire-and-forget khi upload xong chunk. Giải pháp: Bổ sung phương thức `reconcile_publish()` tự động thăm dò `get_post_status` cho đến khi bài đăng đạt `PUBLISH_COMPLETE` hoặc `FAILED`.
8. **Thiếu kiểm tra quyền riêng tư**: Không đối soát `draft.privacy` với danh sách `allowed_privacy_levels` của creator info trước khi gọi Direct Post init. Giải pháp: Chặn sớm trước khi gọi API.
9. **DOM bỏ qua tương tác (comment, duet, stitch)**: Giải pháp: Thêm DOM evaluate script kiểm tra switch/checkbox và toggle theo cấu hình `allow_comment`, `allow_duet`, `allow_stitch`.

## 2. Quy Tắc Bắt Buộc (Mandatory Rules for Future Agents)
- Khi sửa đổi SDK `sammonny`: Luôn đồng bộ đồng thời cả 2 vị trí:
  - Repository nguồn: `D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\sdk\python\sammonny\platforms\tiktok.py`
  - Thư viện runtime: `C:\Users\sonson\AppData\Roaming\Python\Python314\site-packages\sammonny\platforms\tiktok.py`
- Tuyệt đối không bao giờ trả về ID giả dạng `studio_post_` khi không thể xác minh DOM một cách chắc chắn.
- Không bao giờ cho phép một luồng upload tự ý gọi một luồng upload khác (silent fallback) khi bước publish trước đó đã gửi dữ liệu lên CDN/server, vì điều này tạo ra nguy cơ rất cao đăng trùng lặp video.
