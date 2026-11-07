# 073 — Bảng hồ sơ: mọi cột phải là dữ liệu thật trong CSDL

Đã kiểm chứng ngày 2026-11-07: đối chiếu từng ô của @swall.pain với `profiles` trên bản sao CSDL thật (có chạy một lần sync thật).

## Lỗi đã sửa
- **3 cột hiển thị dữ liệu bịa:**
  - "TS" đọc trường không tồn tại nên luôn hiện "Yes".
  - "STT" (cột 25) trùng cột 0.
  - "MP" đọc trường không tồn tại nên luôn 0.
  - Cách sửa: thay bằng **T.Likes** (`total_likes`) và **Shadowban**. Bố cục v2 có 28 cột (0–27); cột 0–23 giữ nguyên vị trí (cột 12 có bộ vẽ trạng thái riêng).
- **Cài đặt ẩn cột lưu theo số thứ tự cột:** được chuyển sang bố cục mới bằng `migrate_hidden_profile_columns` (khoá `profile_columns_version` = "2").
- **Shadowban:** schema mặc định `'safe'`. Chỉ hiển thị khi đã có `traffic_source_json` (tức đã đo), nếu chưa thì hiện "—".
- **T.Views** từng bị ghi đè bằng tổng 30 ngày (296 nghìn thay vì 1,83 triệu). Chuỗi 30 ngày chỉ được ghi vào `views_month`; `total_views` = SUM(views) của mọi video đã biết trong `statisticTable`.
- **Email/Note bị NULL hiện chữ "None"**, nay để trống.
- **CS 1 gậy hiện 🔴**, nay hiện 🟡 cho khớp dialog Sức khoẻ (1 gậy = Warning, từ 2 gậy = High Risk).
- **Số cột gán cứng "28 cột" và "22+ có sẵn":** nay lấy từ danh sách tiêu đề.
- **"Cấu hình luồng check" mất sau mỗi lần khởi động lại:** nay lưu vào QSettings `max_threads`.

## Quy tắc
- Thêm cột mới thì phải: (1) trường đó có trong CSDL; (2) có test đổ dữ liệu cho cột; (3) giá trị mặc định của schema không được hiển thị như một số đo (xem instinct 065).
- Không tham chiếu cột ID bằng số cứng: dùng `PROFILE_COL_ID`.
- Dialog Hướng dẫn sử dụng đang được agent khác viết lại và còn mô tả bố cục cũ (TS / MP / 28. ID). Cần cập nhật theo bố cục v2.

## Rà commit agent khác chiều 2026-11-07 (a1905db, 9e88e18, 3c1bd24, SDK 0476a90 / 600e2c5)
- **a1905db:** bảng hàng đợi hiện cả video `published`, và lệnh "Đặt lại Sẵn sàng / Thử lại" đổi MỌI trạng thái về `available`. Chọn nhầm video đã đăng thì nó bị ĐĂNG LẠI.
  - Đã sửa: `reset_status_to_available` / `assign_profile_to_videos` chỉ đụng tới `available` / `reserved` / `failed`, và thông báo số video bị bỏ qua.
- **SDK bị chép thẳng vào venv mà vẫn mang số 1.8.5:** wheel trong `vendor/` (CI và máy cài mới dùng) là code cũ, nên CI test một SDK khác với SDK app thật sự chạy.
  - Quy tắc: thay SDK thì phải tăng phiên bản → build wheel → đưa vào `vendor/` → ghim trong requirements/pyproject → `pip install --force-reinstall`. So hash file trong venv, repo và wheel để kiểm tra.
- **600e2c5:** chụp màn hình ghi vào `C:\Users\sonson\.gemini\antigravity\...` và log nội dung trang ở mức INFO. Đã gỡ trong 1.8.6, có test vệ sinh trong SDK.
- **Chưa kiểm chứng:** Hybrid ở chế độ riêng tư hoặc bạn bè (`visibility_type` bản mới: private 0 / friends 1 / public 2, ngược với 1.8.5).
- **Chưa làm:** nhãn "AI-generated" không được gửi lên TikTok ở BẤT KỲ phương thức nào (SDK bỏ qua `is_ai_generated`).
