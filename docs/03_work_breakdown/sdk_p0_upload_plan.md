# Kế hoạch P0: nâng cấp SDK để upload video ổn định (ĐÃ TRIỂN KHAI: SDK 1.8.3, 2026-11-07)

Ngày lập: 2026-11-07. Phạm vi: SamMonny SDK `sdk/python/sammonny/platforms/tiktok.py` (bản mới sẽ là 1.8.3) và
phần app TAVM liên quan. Kế hoạch chỉ đụng tới luồng upload và OAuth. Không đụng vân tay, chống phát hiện, chữ ký
request hay captcha.

## 0. Quy tắc chính thức của TikTok (đã đối chiếu tài liệu)

**Content Posting API, FILE_UPLOAD** ([Media Transfer Guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide)):
- Mỗi khối dài **5 MB – 64 MB**. Riêng khối cuối được lớn hơn `chunk_size`, tối đa **128 MB**.
- `total_chunk_count` = `video_size / chunk_size`, **làm tròn xuống**.
- Video **< 5 MB** phải gửi nguyên một khối, với `chunk_size` = kích thước video.
- Có từ 1 tới 1000 khối. Các khối gửi **lần lượt**. File tối đa **4 GB**.
- Header của lệnh PUT: `Content-Type`, `Content-Length`, `Content-Range: bytes first-last/total`.
- Mã trả về:
  - 206: đã nhận khối, còn chờ khối tiếp.
  - 201: đã nhận đủ.
  - 403: `upload_url` đã hết hạn.

**OAuth** ([User Access Token Management](https://developers.tiktok.com/doc/oauth-user-access-token-management)):
- Lệnh làm mới: `POST https://open.tiktokapis.com/v2/oauth/token/`, gửi dạng
  `application/x-www-form-urlencoded`, gồm `client_key`, `client_secret`, `grant_type=refresh_token`, `refresh_token`.
- Phản hồi gồm `access_token`, `expires_in`, `refresh_token`, `refresh_expires_in`, `open_id`, `scope`.
- **Refresh token đổi mới sau mỗi lần làm mới.** Phải lưu token mới. Nếu tiếp tục dùng token cũ, lần làm mới sau sẽ
  thất bại.
- Tài liệu ghi hai bộ thời hạn khác nhau (2 giờ / 180 ngày và 24 giờ / 365 ngày). Vì vậy **không ghi cứng** thời
  hạn nào: luôn dùng `expires_in` và `refresh_expires_in` do TikTok trả về.

## 1. Hiện trạng (lỗi P0)

| # | Lỗi | Vị trí | Hậu quả |
|---|---|---|---|
| A | Chia khối 10 MB cố định, số khối tính bằng làm tròn **lên** | `init_direct_post`, `upload_video_chunks` | Nhiều kích thước file có khối cuối < 5 MB (ví dụ 21 MB thành 10+10+1) nên TikTok từ chối. File < 5 MB vẫn khai `chunk_size` = 10 MB. Không chặn file > 4 GB, không giới hạn 1000 khối. |
| B | Đọc nguyên file vào RAM | Nhánh API chính thức (`raw_bytes = f.read()`), Hybrid (`video_bytes = f.read()`). Pipeline TOS còn chép thêm từng khối. | Video vài GB làm tràn bộ nhớ, nhất là khi nhiều luồng upload cùng lúc. |
| C | Không làm mới token | SDK không có hàm làm mới; app chỉ lưu `access_token` | Token hết hạn sau vài giờ hoặc 1 ngày, nên mọi upload qua API thất bại. |
| C2 | Client key bị lưu vào trường `access_token` của `GLOBAL_API_CONFIG` | `api_cookie_dialog.py` | Dữ liệu lẫn lộn; dễ gửi nhầm client key thay cho token. |
| C3 | `refresh_token` / `client_id` từ nhập hàng loạt nằm trong cột CSDL dạng chữ thường | `profiles.refresh_token` | Lộ bí mật, trái quy định AgentShield. |

## 2. Thiết kế

### P0-A. Chia khối đúng quy tắc (SDK)
- Hàm thuần `plan_direct_post_chunks(video_size, preferred_chunk=10 MB) -> (chunk_size, total_chunk_count)`:
  - Kích thước 0 hoặc > 4 GB: báo lỗi rõ ràng.
  - < 5 MB: `(video_size, 1)`.
  - Còn lại: `chunk_size` kẹp trong khoảng [5 MB, 64 MB]; nếu số khối vượt 1000 thì tăng `chunk_size`.
    `count = floor(size / chunk_size)`; khối cuối = `chunk_size` + phần dư (luôn ≤ 128 MB).
- `init_direct_post` và `upload_video_chunks` dùng **chung** một kế hoạch chia khối, để số khối khai báo khớp đúng
  số khối gửi đi.
- `Content-Type` lấy theo đuôi file (mp4, mov, webm). Xử lý mã trả về: 206 thì tiếp tục, 201 thì xong, 403 thì báo
  "upload_url hết hạn" (lỗi rõ ràng, không thử lại mù quáng).

### P0-B. Đọc file theo khối (SDK)
- `upload_video_chunks` nhận **đường dẫn file** (vẫn nhận `bytes` để tương thích ngược) và đọc từng khối bằng
  `seek` + `read`. RAM chỉ cần cỡ một khối.
- Nhánh API chính thức truyền đường dẫn thay cho `f.read()`.
- Hybrid / TOS:
  - Tính MD5 của cả file bằng cách đọc dần (stream).
  - Chia khối bằng vị trí (offset), không chép dữ liệu.
  - `execute_tos_upload` đọc từng khối khi cần gửi.
  - Giao diện cũ nhận `bytes` vẫn chạy được.

### P0-C. Tự làm mới token (SDK + app)
**SDK:**
- Thêm `TikTokDirectPostClient.refresh_access_token(client_key, client_secret, refresh_token, proxy_url=None)`, trả
  về `TokenSet`. Có proxy.
- Phân loại lỗi:
  - `invalid_grant` (refresh token hết hạn hoặc bị thu hồi): báo "cần đăng nhập lại API".
  - Lỗi mạng: lỗi tạm thời, thử lại được.

**App: thêm `TokenManager`:**
- Hàm `get_valid_access_token(profile_id)` làm mới token khi chỉ còn dưới 5 phút là hết hạn, hoặc khi chưa rõ hạn.
- **Khóa theo từng hồ sơ**: hai lượt upload song song không được làm mới cùng lúc, vì refresh token xoay vòng nên
  lần làm mới thứ hai sẽ thất bại.
- **Lưu token mới vào Vault trước** rồi mới dùng: lưu `refresh_token` mới, `expires_at`, `refresh_expires_at`. Nếu
  lưu thất bại thì báo lỗi rõ ràng, không để token mới chỉ nằm trong RAM.
- Gặp 401 khi gọi API: làm mới **một lần** rồi thử lại lệnh đó.
- Lệnh làm mới đi qua **proxy của hồ sơ**, theo luật egress hiện có.

**App: sửa cách lưu trữ:**
- Client key và client secret lưu đúng trường (`client_key`, `client_secret`). Vẫn đọc được định dạng cũ.
- Chuyển `profiles.refresh_token` / `client_id` dạng chữ thường vào Vault ở lần dùng đầu, rồi xóa khỏi CSDL.
- Refresh token hết hạn hoặc bị thu hồi: hồ sơ được đánh dấu "Cần kết nối lại TikTok API", upload báo lỗi rõ ràng.

**Ngoài phạm vi P0 (để P1):** luồng đăng nhập OAuth để lấy token lần đầu. Hiện token được dán tay hoặc nhập hàng loạt.

## 3. Thứ tự làm (TDD, mỗi bước có test viết trước)

| Pha | Nội dung | Test chính |
|---|---|---|
| 1 | `plan_direct_post_chunks` + init/upload dùng chung | Bảng kích thước: 1 MB, 4,99 MB, 5 MB, 21 MB, 25 MB, 64,5 MB, 3,9 GB (chỉ tính toán), 4 GB + 1 (từ chối), trường hợp > 1000 khối. Khối cuối ≥ 5 MB và ≤ 128 MB. |
| 2 | Đọc theo khối: API chính thức + Hybrid/TOS | Đo `tracemalloc` khi upload file tạm 200 MB qua server giả: RAM đỉnh < 3 × khối. Không còn lệnh đọc nguyên file. Header `Content-Range` đúng. |
| 3 | SDK `refresh_access_token` | Server OAuth giả: đúng định dạng form, nhận đúng `TokenSet`, `invalid_grant` thành lỗi "cần đăng nhập lại", có đi qua proxy. |
| 4 | App `TokenManager` + Vault + chuyển dữ liệu CSDL | Token mới được lưu trước khi dùng. Hai luồng chỉ làm mới một lần. Gặp 401 thì làm mới một lần rồi thử lại. Cột chữ thường được xóa. Không ghi Vault thật trong test. |
| 5 | Nối vào adapter upload + giao diện báo "cần kết nối lại" | Upload qua API dùng token đã làm mới. Hồ sơ hết hạn refresh được đánh dấu. |
| 6 | Kiểm định | Test SDK + test app. E2E với server TikTok **giả cục bộ** cho cả chia khối lẫn làm mới token (không gọi TikTok thật). Đóng gói SDK 1.8.3, ghim phiên bản trong app, build lại exe. |

## 4. Rủi ro và cách xử lý

- **Tài liệu TikTok không thống nhất về thời hạn token:** dùng giá trị TikTok trả về và làm mới sớm 5 phút.
- **Tranh chấp khi refresh token xoay vòng:** khóa theo từng hồ sơ, và lưu token mới trước khi dùng.
- **Hybrid là API nội bộ, không công khai:** P0 chỉ đổi cách đọc file, không đổi giao thức.
- **Không thể thử với TikTok thật** nếu chưa có ứng dụng TikTok đã được duyệt cùng tài khoản thử: kiểm chứng bằng
  server giả theo đúng đặc tả. Cần bạn thử trên một tài khoản thật sau khi giao.

## 5. Cần bạn chốt

- **D1:** Làm mới sớm bao lâu trước khi token hết hạn. Đề xuất 5 phút.
- **D2:** Client key và client secret dùng **một bộ chung** cho cả app (hộp thoại Cấu Hình API) hay **riêng từng hồ
  sơ** (bản nhập hàng loạt có cột `client_id`). Đề xuất: một bộ chung, nhưng hồ sơ nào có `client_id` riêng thì ưu
  tiên dùng của hồ sơ đó.
- **D3:** Phiên bản SDK mới là 1.8.3 (cài lại vào app và build lại exe khi xong).

## 6. Kết quả triển khai

- Đã duyệt D1–D3 như đề xuất. P0-A, P0-B (API chính thức) và P0-C đã xong, kèm test viết trước.
  - SDK: 188/188 test.
  - App: 607/607 test.
  - E2E với server TikTok giả: PASS (3 / 21 / 64,5 MB thành 1 / 2 / 6 khối; dữ liệu nhận đúng từng byte; làm
    mới token đúng 1 lần; lưu đúng refresh token mới).
- **Lệch so với kế hoạch: Hybrid không được làm "đọc theo khối".** Pipeline TOS của Hybrid không upload thật: nó
  chỉ giả lập việc truyền với URL `tiktokcdn.com` do chính nó dựng, và dựa vào việc ký request giả lập thiết bị.
  Tối ưu bộ nhớ cho một đường truyền giả là vô nghĩa, và phần ký request nằm ngoài phạm vi hỗ trợ. Chỉ API chính
  thức thật sự đăng được video.
