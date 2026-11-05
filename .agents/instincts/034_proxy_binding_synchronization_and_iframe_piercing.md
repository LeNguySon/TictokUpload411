# Bản Năng Kỹ Thuật: 034 — Đồng Bộ Tuyệt Đối Proxy Binding & Thuật Toán Xuyên Iframe Studio

## Bối Cảnh (Context)
Khi tích hợp xuất bản video lên TikTok bằng mô hình Tri-Modal Hybrid (kết hợp Python API, trình duyệt GoLogin Orbita, và Headless Studio DOM):
1. **Rò rỉ IP qua Python `requests`**: Nếu `requests.Session()` tạo mặc định mà không nạp proxy từ database, dữ liệu video chunk hoặc API call sẽ gửi trực tiếp từ IP máy thật (Việt Nam) trong khi trình duyệt chạy qua Proxy profile (US/UK) $\rightarrow$ TikTok WAF phát hiện lệch IP và áp đặt lệnh phạt hoặc bóp tương tác kênh.
2. **Iframe Form Upload**: Giao diện upload video trên TikTok Creator Center (`https://www.tiktok.com/creator-center/upload`) đặt thẻ `<input type="file">` bên trong một thẻ `<iframe>`. Lệnh CDP `DOM.querySelector` ở document gốc sẽ không tìm thấy.
3. **Nút Post Bị Khóa (Disabled)**: Trong khi video đang được tải lên và kiểm tra bản quyền âm thanh (Copyright Check), nút "Post" mang thuộc tính `disabled="true"`. Bấm chuột ngay lập tức sẽ không có tác dụng.
4. **SecSDK Captcha Slider**: Thử thách kéo thanh trượt ghép hình của ByteDance WAF nếu không được phát hiện sớm sẽ gây kẹt vô hạn tiến trình.

---

## Giải Pháp Kỹ Thuật Chuẩn Công Nghiệp (Standardized Pattern)

### 1. Đồng Bộ Proxy Tuyệt Đối 2 Chiều (Dual-Channel Proxy Binding)
- **Tầng Trình Duyệt**: Trước khi khởi động tab GoLogin, gọi `OrbitaLauncher().sync_daemon_profile_proxy(profile_uuid, proxy_data)` để ghi đè proxy vào `Default/Preferences` (`gologin["proxy"]`).
- **Tầng Python API**: Trích xuất `proxy_url` (`proto://user:pass@host:port`) và gán thẳng vào `requests.Session()`:
  ```python
  sess.proxies = {"http": proxy_url, "https": proxy_url}
  ```
- Mọi luồng API (Direct Post, TOS Chunk Streaming Phase 2) đều phải tiếp nhận `proxy_url` và bắt buộc chạy qua proxy cấu hình.

### 2. Thuật Toán Xuyên Iframe CDP (CDP Iframe Piercing)
- Sử dụng CDP `DOM.getDocument(depth=-1, pierce=True)` để lấy cây DOM phẳng xuyên qua toàn bộ shadow roots và child iframes.
- Hàm đệ quy `extract_file_input_node_id(nodes)` duyệt xuyên qua `children`, `shadowRoots`, và `contentDocument` để bốc chính xác `nodeId` của `<input type="file">` và đính kèm video qua `DOM.setFileInputFiles`.

### 3. Thăm Dò Nút Post Sẵn Sàng (Ready State Polling)
- Thăm dò tối đa 12 chu kỳ (6–30s) bằng JS evaluate kiểm tra `btn.disabled || btn.classList.contains('disabled')`.
- Chỉ thực hiện click sinh học (Minimum Jerk / WindMouse) khi nút Post chuyển sang trạng thái `enabled`.

### 4. Bắt Popup Captcha Sớm
- Đánh giá biểu thức JS:
  ```javascript
  !!(document.querySelector('.captcha-verify-container') ||
     document.querySelector('.secsdk-captcha-drag-wrapper') ||
     document.querySelector('div[class*="captcha"]'))
  ```
- Nếu phát hiện, lập tức ghi log cảnh báo và không treo ngầm tiến trình.

