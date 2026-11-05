# Instinct 032: V8 Fetch Origin Context and Relative URL Resolution in GoLogin/Orbita

## 1. Bản Chất Kỹ Thuật (Root Cause of Status 0 / Code -1)
- Khi gọi `CDPLiveSigner.execute_in_browser_fetch` để thực thi `window.fetch(endpoint)` trong nhân V8 Chromium, nếu tab trình duyệt đang ở `about:blank` hoặc chưa điều hướng tới domain `tiktok.com`:
  1. **Lỗi phân giải URL tương đối**: `fetch("/tiktok/web/project/post/v1/...")` trên `about:blank` bị Chromium ném ngoại lệ:
     `TypeError: Failed to execute 'fetch' on 'Window': Failed to parse URL from /tiktok/web/...`
  2. **Thiếu ngữ cảnh Cookie & CSRF**: Trên `about:blank`, `document.cookie` rỗng hoàn toàn, không có `sessionid`, `msToken` hay `passport_csrf_token`.
  3. **Không tải Web SDK Hook của ByteDance**: Các tệp bảo mật `webmssdk.js` / `bdms.js` chỉ nạp khi trang ở domain `tiktok.com`.

## 2. Giải Pháp Xử Lý Triệt Để (Architectural Fix)
1. **Kiểm tra và thiết lập Origin Context**:
   Trước khi thực thi Phase 3 (V8 Fetch Injection), kiểm tra URL hiện tại của tab trình duyệt. Nếu chưa thuộc domain `tiktok.com`, điều hướng tới `https://www.tiktok.com/creator-center/upload?from=upload`:
   ```python
   current_url = str(self.session.cdp.evaluate("window.location.href") or "")
   if not current_url or "tiktok.com" not in current_url:
       self.session.navigate(TikTokHeadlessStudioUploader.STUDIO_UPLOAD_URL)
       time.sleep(2.0)
   ```
2. **Kế thừa Cookie & CSRF tự nhiên**:
   Khi tab đã ở `tiktok.com`, `window.fetch()` tự động phân giải đường dẫn tương đối thành URL tuyệt đối `https://www.tiktok.com/...`, tự động gắn cookie phiên đăng nhập và kích hoạt các hook của ByteDance Web SDK để tạo chữ ký hợp lệ.
3. **Truyền tham số `schedule_time` vào `post_payload`**:
   Đóng gói epoch timestamp của lịch hẹn vào `post_common_info["schedule_time"]` và chuyển `post_type` sang chế độ scheduled post.
