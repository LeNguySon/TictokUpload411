# Bản Năng Kỹ Thuật: 035 — Tái Cấu Trúc Phi Trạng Thái Đa Luồng (Stateless Multi-Threaded Upload Adapter)

## Bối Cảnh (Context)
Trong ứng dụng PyQt6 đa luồng, khi nhiều worker thread (`UploadWorker`) được kích hoạt song song trên `QThreadPool` để tải lên các video khác nhau cho các tài khoản TikTok khác nhau:
1. **Lỗi Race Condition**: Cả ứng dụng chia sẻ một thực thể `SamMonnyTikTokAdapter` và `TikTokPublisherAdapter`. Trước đây, hàm `upload_video()` ghi đè thuộc tính `self.publisher.preferred_mode = UploadMode.COOKIE_API_HYBRID` hoặc `OFFICIAL_DIRECT_POST` trực tiếp lên đối tượng dùng chung.
2. **Khóa luồng cục bộ không che chắn được Adapter**: Khóa `get_profile_upload_lock(profile_id)` chỉ khóa trên từng profile riêng biệt, nên hai profile upload song song sẽ chạy đồng thời và ghi đè chế độ của nhau (Profile có OAuth bị đẩy sang Cookie Hybrid hoặc ngược lại).
3. **Xung đột session factory**: Việc monkey-patching `self.publisher.session_factory` và khôi phục trong `finally` dẫn đến việc luồng này đóng hoặc làm mất session của luồng kia.

---

## Giải Pháp Kỹ Thuật Chuẩn Công Nghiệp (Standardized Pattern)

### 1. Kiến Trúc Phi Trạng Thái (Stateless Delegation)
- Tuyệt đối **không lưu trữ hoặc thay đổi mutable state** (`preferred_mode`, `session_factory`) trên adapter dùng chung trong quá trình upload.
- Truyền `preferred_mode: Optional[UploadMode] = None` trực tiếp qua chữ ký hàm:
  ```python
  def upload(self, draft: DraftResult, account_id: str, ..., preferred_mode: Optional[UploadMode] = None) -> UploadResult:
      cap = self.validate_capability(account_id, preferred_mode=preferred_mode)
  ```
- Biến `effective_mode` được tính toán trong stack frame cục bộ của luồng gọi và truyền đi mà không làm thay đổi trạng thái instance.

### 2. Quản Lý Vòng Đời Session Cục Bộ Trong Hàm (Local Lifecycle Management)
- `TikTokPublisherAdapter.upload()` tự khởi tạo session từ `self.session_factory(account_id)` và tự đóng trong khối `try...finally` cục bộ:
  ```python
  session = None
  try:
      if cap.mode == UploadMode.COOKIE_API_HYBRID:
          session = self.session_factory(account_id)
          ...
  finally:
      if session and hasattr(session, "close"):
          session.close()
  ```
- Loại bỏ hoàn toàn mọi cơ chế monkey-patching bên ngoài.

