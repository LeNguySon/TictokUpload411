# Đặc Tả Giao Diện Người Dùng (UI/UX Specification)
## Bố Cục Bảng Kép Chuẩn Windows 11 Fluent Design System 2.0 (Dual-Table Layout)

Tài liệu này quy chuẩn toàn bộ hệ thống giao diện người dùng theo chuẩn **Windows 11 Fluent Design System 2.0**, sử dụng thư viện `PyQt6` và `PyQt-Fluent-Widgets`, bám sát 100% bố cục thực tế từ công cụ quản lý & reup TikTok (Bảng Profiles ở trên, Bảng Videos ở dưới).

---

## 1. Triết Lý Thiết Kế & Bố Cục Tổng Thể

Giao diện chính được chia thành 2 khu vực bảng dữ liệu trung tâm, ngăn cách bởi một thanh trượt (`QSplitter` phong cách Fluent) cho phép người dùng tùy biến tỉ lệ linh hoạt:

```
+======================================================================================================================+
| [FluentIcon] TikTok Studio Manager v2.0 - [Dự án mặc định]                     [Q Tìm kiếm nhanh (Ctrl+F)] [_] [O] [X]|
+----------------------------------------------------------------------------------------------------------------------+
| [Menu: File v] [Dự Án v] [Công Cụ v] [Dọn Trình Duyệt] [Thùng Rác] [Cài Đặt]                  [Theme: [Light / Dark] ]|
+----------------------------------------------------------------------------------------------------------------------+
| [ Dự Án: [Dự án mặc định  v] ] [IconCam] [IconVideo] [IconGear] | [Luồng: [ 10 ]-+] [ Q Tìm ID, email, proxy... ]   |
| [ + Thêm 1 Profile ] [ ++ Thêm Nhiều ] [ Hiện Tất Cả ] [ Mở Browser (GoLogin/Chrome) ]                                |
+----------------------------------------------------------------------------------------------------------------------+
| BẢNG 1: QUẢN LÝ HỒ SƠ TÀI KHOẢN (Profiles Table - Fluent Style)       [Preset: (x) Tất cả  ( ) Doanh Thu  ( ) Kỹ Thuật]|
|----------------------------------------------------------------------------------------------------------------------|
| [v] | Avt  | Tên Hồ Sơ  | Logged | Proxy          | ID TikTok     | Views(30d) | Flw  | LIVE  | $Earned | KYC | Ghi Chú |
|----------------------------------------------------------------------------------------------------------------------|
| [x] | (•)  | US_Beta_01 | [Yes]  | http:192.168.1 | @stirkjaulerc | 24,360     | 13   | [LIVE]| $145.20 | [No]| Main US |
| [ ] | (•)  | US_Beta_02 | [Yes]  | http:10.0.0.12 | @otwaylsari   | 43,586     | 94   | [LIVE]| $320.00 | [No]| Beta UK |
+======================================================================================================================+
| ======= [===] Thanh trượt QSplitter (Kéo mở rộng hoặc Click nút [v] để thu gọn/mở nhanh) [===] =======================|
+======================================================================================================================+
| BẢNG 2: DANH SÁCH & HÀNG ĐỢI VIDEO  |  [ Đã chọn 1 / 7,122 video ]                   [ Q Tìm video theo tiêu đề... ]  |
| [ Icon Folder ] [ Icon Render ] [ Lên Lịch Đăng ] [ Nhảy dòng: [ 0 ] ]               [ Xóa Bảng ] [ Tự Động: (ON) ]  |
|----------------------------------------------------------------------------------------------------------------------|
| STT | Tiêu Đề Video       | View | Like | Thời Lượng | Chế Độ   | Lên Lịch Đăng    | Kênh Gán   | Tiến Độ (Source)       |
|----------------------------------------------------------------------------------------------------------------------|
| 1   | Cooking Master Ep 1 | 12k  | 1.4k | 00:00:45   | [Public] | 2026-11-04 19:00 | US_Beta_01 | [======== 100% ======] |
| 2   | Gadget Review 2026  | 85k  | 9.2k | 00:01:10   | [Public] | 2026-11-04 20:30 | US_Beta_02 | [==== 55%           ] |
+----------------------------------------------------------------------------------------------------------------------+
| [Status Card] Xin chào: peps | Bản quyền: Gôepro (Hạn: 07-08-2026) | v1.5.5.2         [v] Dọn cache dự án khi thoát  |
+======================================================================================================================+
```

---

## 2. Đặc Tả Chi Tiết Bảng 1: Quản Lý Hồ Sơ (Profiles Table - 28 Cột MMO)

### 2.1 Danh Mục 28 Cột Dữ Liệu & Quy Tắc Render Chuẩn Windows 11 Fluent

| STT | Tên Cột | Trường CSDL | Widget / Delegate Fluent | Hành Vi Tương Tác & Hiển Thị |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **Avt** | `avatar_url` / `avatar_path` | `RoundPixmapDelegate` (28x28px) | Ảnh đại diện tròn bo góc mịn, hover phóng to nhẹ |
| 2 | **Tên hồ sơ** | `name` | `BodyStrongLabel` (Segoe UI 13px) | Nhấn đúp / F2 để đổi tên nhanh |
| 3 | **Logged** | `state_loggin_browser` | `PillBadge` (Yes: Xanh dịu, No: Xám) | Chỉ báo trạng thái đăng nhập trên trình duyệt |
| 4 | **Proxy** | `proxies.host:port` | `CaptionLabel` | Rút gọn `host:port`; click mở dialog chi tiết |
| 5 | **Type** | `proxies.type` | Text tag (`http`, `socks5`) | Loại giao thức kết nối proxy |
| 6 | **ID Tiktok** | `username_on_tiktok` | `HyperlinkButton` styled | Click để sao chép username; mở kênh trên trình duyệt |
| 7 | **Views(30d)** | `views_month` | Numeric formatted (`24,360`) | Sắp xếp tăng/giảm |
| 8 | **T.Follows** | `total_followers` | Numeric formatted (`13`) | Tổng số follower hiện tại |
| 9 | **T.Views** | `total_views` | Numeric formatted (`24,360`) | Tổng view toàn kênh |
| 10 | **T.Video** | `total_videos` | Numeric formatted (`118`) | Số lượng video đã xuất bản |
| 11 | **Email** | `email` | Masked text (`a***@gmail.com`) | Bị che tự động; click xem đầy đủ |
| 12 | **Tình trạng** | `status` | `InfoBadge` Fluent | - `LIVE`: Xanh ngọc pastel<br/>- `DIE`: Đỏ san hô pastel<br/>- `CHECKPOINT`: Cam hổ phách |
| 13 | **Cookie** | `tokens.cookie` (Vault) | Masked dots (`••••••••`) | Tự động che an toàn; không hiển thị plaintext |
| 14 | **$Earned** | `earned_amount` | Currency formatted (`$145.20`) | Màu xanh lá nhấn mạnh doanh thu quỹ |
| 15 | **$Balance** | `balance` | Currency formatted (`$50.00`) | Số dư khả dụng rút về tài khoản |
| 16 | **CS** | `creativity_status` | Status Tag (`Beta`, `Rewards`) | Trạng thái tham gia Quỹ sáng tạo |
| 17 | **RPM** | `rpm` | Number (`$0.85`) | Doanh thu trung bình trên mỗi 1,000 views |
| 18 | **QG** | `country_code` | Quốc kỳ / Mã quốc gia (`US`, `UK`, `FR`) | Quốc gia đăng ký kênh |
| 19 | **KYC** | `kyc_status` | Badge (`Yes`, `No`) | Trạng thái xác minh danh tính |
| 20 | **Note** | `notes` | Editable Text Cell | Ghi chú nhanh cho profile, bấm Enter để lưu |
| 21 | **Re.Apply** | `reapply_date` | Date Label (`2026-11-20`) | Ngày được quyền nộp lại đơn tham gia quỹ |
| 22 | **PRIVACY** | `default_privacy` | Tag (`PUBLIC`, `PRIVATE`) | Quyền riêng tư mặc định khi xuất bản |
| 23 | **VAT** | `tax_status` | Tag (`Yes`, `No`) | Trạng thái khai báo thuế |
| 24 | **TS** | `verified_badge` | Icon huy hiệu | Tích xanh / Tích sao TikTok |
| 25 | **STT** | Row index | Số thứ tự | Tự động đánh số theo hàng hiển thị |
| 26 | **VVP** | `copyright_strikes` | Badge cảnh báo (`0`, `1`, `2`) | Số gậy vi phạm bản quyền / chính sách |
| 27 | **MP** | `secondary_pin` | Masked (`•••`) | Mã PIN hoặc mật khẩu thứ hai nếu có |
| 28 | **ID** | `id` | Dimmed label | Khóa chính CSDL (Primary Key) |

### 2.2 Bộ Lọc Nhóm Cột Thông Minh (Column Preset Chips)
Nhằm giải quyết vấn đề "bội thực thông tin" khi phải cuộn ngang qua 28 cột, giao diện cung cấp 3 chế độ xem nhanh:
1. **Tổng Quan (Overview)**: Hiện các cột thiết yếu (`Avt`, `Tên hồ sơ`, `Logged`, `Proxy`, `ID Tiktok`, `Tình trạng`, `Note`).
2. **Chỉ Số & Doanh Thu (Monetization)**: Tập trung theo dõi MMO (`ID Tiktok`, `Views(30d)`, `T.Follows`, `$Earned`, `$Balance`, `CS`, `RPM`, `KYC`).
3. **Kỹ Thuật & Mạng (Network & Security)**: Phục vụ quản trị proxy và token (`Tên hồ sơ`, `Proxy`, `Type`, `Logged`, `Cookie`, `Email`, `VAT`, `VVP`).
4. **Toàn Bộ (All Columns)**: Mở toàn bộ 28 cột như giao diện truyền thống.

---

## 3. Đặc Tả Chi Tiết Bảng 2: Danh Sách & Hàng Đợi Video (Upload Table)

### 3.1 Thanh Tác Vụ Con (Mid Action Bar)
- **Chỉ báo số lượng**: `BodyStrongText` định dạng: `Đã chọn [X] / [Y] video` với màu Accent Blue `#0078D4`.
- **Nút Import Thư Mục**: Icon thư mục Fluent để tải hàng loạt file video từ máy tính.
- **Nút Render / Xử Lý Video**: Icon công cụ để chuyển đổi độ phân giải, lách âm thanh hoặc cắt lát video.
- **Nút Lên Lịch Đăng**: `PrimaryPushButton` bo góc 6px, mở dialog cấu hình thời gian giãn cách giữa các bài đăng.
- **Nhảy Dòng (Enter)**: `SpinBox` bo góc Fluent điều chỉnh bước nhảy lựa chọn.
- **Ô Tìm Kiếm Video**: `SearchLineEdit` tìm kiếm tức thì theo tiêu đề video.
- **Nút Xóa Bảng**: `TransparentToolButton` với hiệu ứng màu đỏ nhẹ khi hover.

### 3.2 Cột Dữ Liệu Bảng Video

| Cột | Thuộc Tính | Widget / Delegate | Mô Tả |
| :--- | :--- | :--- | :--- |
| **STT** | Row index | Center Label | Thứ tự video trong hàng đợi |
| **Tiêu đề** | `title` / `caption` | `BodyLabel` Semibold | Tiêu đề và hashtag mô tả video |
| **Lượt view** | `views` | Numeric formatted | Số view đạt được sau khi đăng (hoặc view gốc) |
| **Lượt like** | `likes` | Numeric formatted | Số like đạt được |
| **Duration** | `duration` | Monospace Label (`00:00:45`) | Thời lượng video (hh:mm:ss) |
| **Hiển thị** | `visibility` | `ComboBox` / `PillBadge` | Chế độ đăng: `Public`, `Friends`, `Private` |
| **Lên lịch** | `schedule_time` | DateTime Label | Thời gian dự kiến xuất bản tự động |
| **Upload To** | `assigned_profile` | Fluent Badge | Tên hồ sơ TikTok được gán đăng video này |
| **Tình trạng** | `status` | Status Badge | `Downloaded`, `Ready`, `Uploading`, `Done`, `Failed` |
| **Source** | `progress` | `ProgressBar` Fluent bo góc | Thanh tiến độ tải lên/render mượt mà (0 - 100%) |
| **Link gốc** | `source_url` | Hyperlink label | Đường dẫn video nguồn (Reup source) |
| **ID Video** | `video_id` | Text copyable | ID video trên TikTok sau khi đăng thành công |
| **PVF URL** | `preview_video_url` | Linkable label | Đường dẫn xem trước video đã xử lý |
| **PAF URL** | `preview_audio_url` | Linkable label | Đường dẫn âm thanh xử lý đi kèm |

---

## 4. Thanh Trạng Thái Đáy (Footer Status Card)

- Thiết kế dưới dạng một dải Card nổi mỏng, gắn liền đáy cửa sổ với hiệu ứng viền mờ của Windows 11.
- **Khu vực bên trái**:
  - `CaptionLabel`: Lời chào người dùng (`Xin chào: peps`).
  - `InfoBadge` bảo mật: Thời hạn bản quyền (`Hạn: 07-08-2026 | Gôepro`).
  - `Tag`: Phiên bản ứng dụng (`Version: 1.5.5.2`).
- **Khu vực bên phải**:
  - `CheckBox` hoặc `SwitchButton` Fluent bo góc: *"Dọn cache tất cả dự án trước khi thoát"*.

---

## 5. Quy Chuẩn Màu Sắc & Fluent Design Tokens (Theme Specifications)

| Token Thiết Kế | Chế Độ Sáng (Light Theme) | Chế Độ Tối (Dark Theme) |
| :--- | :--- | :--- |
| **Nền cửa sổ (Mica Background)** | `#F3F3F3` (Mica Alt) | `#202020` (Mica Dark) |
| **Nền Container Bảng (Card)** | `#FFFFFF` | `#2D2D2D` |
| **Màu Nhấn (Accent Color)** | `#0078D4` (Windows Blue) | `#4CC2FF` (Vibrant Blue) |
| **Trạng Thái LIVE (Success)** | Nền: `#DFF6DD` / Chữ: `#107C41` | Nền: `#103B1E` / Chữ: `#54B054` |
| **Trạng Thái DIE (Danger)** | Nền: `#FDE7E9` / Chữ: `#A80000` | Nền: `#441416` / Chữ: `#FF6B6B` |
| **Trạng Thái Cảnh Báo (Warning)** | Nền: `#FFF4CE` / Chữ: `#795B00` | Nền: `#433519` / Chữ: `#FCE100` |
| **Đường Ngăn Cách (Border/Divider)**| `#E5E5E5` (Solid 1px) | `#383838` (Solid 1px) |
| **Font Chữ Hệ Thống** | `Segoe UI Variable Text` / `Segoe UI` | `Segoe UI Variable Text` / `Segoe UI` |
