"""
User Guide Dialog: In-app interactive documentation, 28 MMO column definitions, and operational runbook.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    PushButton,
)

from src.presentation.dialogs.dialog_cache import ReusableDialogMixin
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    style_tab_widget,
)

INDUSTRIAL_GUIDE_CSS = """
body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    color: #201F1E;
    line-height: 1.6;
    background-color: #FFFFFF;
}
h1 {
    color: #0078D4;
    font-size: 18px;
    font-weight: 600;
    margin-top: 4px;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid #0078D4;
}
h2 {
    color: #106EBE;
    font-size: 15px;
    font-weight: 600;
    margin-top: 16px;
    margin-bottom: 8px;
}
h3 {
    color: #005A9E;
    font-size: 13px;
    font-weight: 600;
    margin-top: 12px;
    margin-bottom: 6px;
}
p {
    margin-top: 4px;
    margin-bottom: 8px;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
}
th {
    background-color: #F3F2F1;
    color: #323130;
    font-weight: 600;
    border: 1px solid #D2D0CE;
    padding: 7px 10px;
    text-align: left;
}
td {
    border: 1px solid #EDEBE9;
    padding: 6px 10px;
}
tr:nth-child(even) {
    background-color: #FAF9F8;
}
code {
    background-color: #F3F3F3;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    border: 1px solid #E1DFDD;
    padding: 2px 5px;
    border-radius: 3px;
    color: #D13438;
}
blockquote {
    border-left: 4px solid #0078D4;
    padding: 8px 14px;
    margin: 10px 0;
    background-color: #F8F9FA;
    color: #323130;
}
ul, ol {
    margin-top: 4px;
    margin-bottom: 8px;
    padding-left: 20px;
}
li {
    margin-bottom: 5px;
}
.badge-blue {
    background-color: #EBF3FC;
    color: #0078D4;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
}
.badge-green {
    background-color: #DFF6DD;
    color: #107C10;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
}
.badge-orange {
    background-color: #FFF4CE;
    color: #797673;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
}
"""

USER_GUIDE_CONTENT = {
    "quick_start": """
<h1>HƯỚNG DẪN BẮT ĐẦU NHANH VÀ VẬN HÀNH HỆ THỐNG</h1>
<p>Chào mừng bạn đến với <b>SonBetaPro (TAVM-2026-WIN)</b> — Nền tảng tự động hóa quản trị và phân phối video TikTok đa luồng chuẩn Windows 11 Fluent UI, phân tầng Clean Architecture kết hợp SamMonny Tri-Modal SDK.</p>

<blockquote>
<b>Nguyên tắc an toàn số 1 (AgentShield Strict Proxy Gate):</b> Để bảo vệ tài khoản tuyệt đối không bị quét vi phạm thuật toán mạng, hãy luôn gán Proxy cho từng hồ sơ trước khi đồng bộ số liệu hoặc bắt đầu tải video lên.
</blockquote>

<h2>Quy Trình 5 Bước Vận Hành Chuẩn Công Nghiệp:</h2>
<ol>
<li><b>Bước 1: Quản Lý Dự Án và Chiến Dịch</b><br>
Mở menu <code>Cài Đặt</code> &gt; <code>Quản lý Dự án / Chiến dịch</code> để phân nhóm các dòng kênh theo từng mục tiêu (Ví dụ: <i>Beta Quỹ Mỹ</i>, <i>Affiliate Shop</i>, <i>Reup Highlight</i>, <i>Kênh Thương Hiệu</i>). Bạn có thể gán thư mục video mặc định cho từng dự án để tự động phân bổ nguồn video.</li>

<li><b>Bước 2: Nạp và Kiểm Định Proxy Tự Động</b><br>
Mở <code>Công cụ Proxy &amp; Leak Audit</code>, dán danh sách proxy định dạng <code>host:port:user:pass</code> hoặc <code>host:port</code>. Hệ thống tự động kiểm tra độ trễ (Ping), xác thực vị trí địa lý quốc gia (US, UK, DE, FR, VN...) và kích hoạt tường lửa chống rò rỉ IP máy thật.</li>

<li><b>Bước 3: Nhập Hồ Sơ (Profiles) Hàng Loạt</b><br>
Sử dụng chức năng <code>Add nhiều profile</code> với cú pháp phân tách: <code>Tên|Email|Mật khẩu|Cookie|Proxy</code>. Toàn bộ mật khẩu, cookie và token phiên làm việc được mã hóa phần cứng bằng Windows DPAPI Credential Vault.</li>

<li><b>Bước 4: Nạp Video và Lên Lịch Tự Động Thông Minh</b><br>
Bấm <code>Thêm Video</code> hoặc chọn cả thư mục video. Sử dụng tính năng <code>Lên lịch</code> để cấu hình thời gian đăng so le (Staggered Scheduling) kèm độ lệch ngẫu nhiên (Jitter) nhằm phân tán lưu lượng và vượt qua thuật toán phát hiện bot của TikTok.</li>

<li><b>Bước 5: Kích Hoạt Upload Đa Luồng</b><br>
Chọn các hồ sơ trên bảng danh sách và bấm <code>Bắt đầu Upload</code>. Hệ thống sẽ điều phối tác vụ qua bộ điều phối đa luồng <code>QThreadPool</code>, đảm bảo giao diện luôn mượt mà và hiển thị tiến độ thời gian thực.</li>
</ol>
""",
    "mmo_columns": """
<h1>TRA CỨU TOÀN DIỆN 28 CỘT MMO VÀ RADAR KÊNH</h1>
<p>Bảng hồ sơ được thiết kế theo đúng chuẩn SSMATool Parity với 28 trường dữ liệu chuyên sâu phục vụ quản trị mạng lưới kênh quy mô lớn:</p>

<table>
<thead>
<tr>
<th>Cột</th>
<th>Tên Chỉ Số</th>
<th>Ý Nghĩa Chuyên Sâu</th>
<th>Định Dạng Dữ Liệu</th>
</tr>
</thead>
<tbody>
<tr><td><b>0. STT</b></td><td>Số thứ tự</td><td>Chỉ số thứ tự hàng trong danh sách hiển thị.</td><td>Số nguyên (1, 2, 3...)</td></tr>
<tr><td><b>1. Avt</b></td><td>Ảnh đại diện</td><td>Avatar kênh TikTok được hiển thị dưới dạng hình tròn bo góc.</td><td>Hình ảnh / Icon</td></tr>
<tr><td><b>2. Tên hồ sơ</b></td><td>Tên Profile</td><td>Tên định danh quản lý nội bộ trên máy tính.</td><td>Chuỗi ký tự</td></tr>
<tr><td><b>3. Logged</b></td><td>Đăng nhập</td><td>Trạng thái xác thực phiên làm việc (Có Cookie hoặc OAuth Token).</td><td><span class="badge-green">YES</span> / <span class="badge-orange">NO</span></td></tr>
<tr><td><b>4. Proxy</b></td><td>Địa chỉ IP</td><td>Proxy gán tĩnh cho hồ sơ nhằm bảo vệ địa chỉ IP máy thật.</td><td><code>IP:Port</code></td></tr>
<tr><td><b>5. Type</b></td><td>Loại Proxy</td><td>Giao thức kết nối mạng của proxy.</td><td><code>HTTP</code> / <code>SOCKS5</code></td></tr>
<tr><td><b>6. ID Tiktok</b></td><td>TikTok Handle</td><td>Tên định danh chính thức trên TikTok (Username bắt đầu bằng <code>@</code>).</td><td><code>@username</code></td></tr>
<tr><td><b>7. Views(30d)</b></td><td>Lượt xem 30 ngày</td><td>Tổng lượt xem video hợp lệ trong 30 ngày gần nhất.</td><td>K / M views</td></tr>
<tr><td><b>8. T.Follows</b></td><td>Tổng Follower</td><td>Tổng số lượng người theo dõi kênh tại thời điểm hiện tại.</td><td>Số nguyên (K / M)</td></tr>
<tr><td><b>9. T.Views</b></td><td>Tổng Lượt Xem</td><td>Tổng số lượt xem tích lũy của toàn bộ video trên kênh.</td><td>Số nguyên (K / M)</td></tr>
<tr><td><b>10. T.Video</b></td><td>Tổng Số Video</td><td>Số lượng video đang công khai trên kênh.</td><td>Số nguyên</td></tr>
<tr><td><b>11. Email</b></td><td>Hộp thư</td><td>Email đăng ký hoặc email khôi phục tài khoản.</td><td>Địa chỉ email</td></tr>
<tr><td><b>12. Tình trạng</b></td><td>Trạng thái</td><td>Trạng thái hoạt động của kênh.</td><td><code>LIVE</code>, <code>DIE</code>, <code>CHECKPOINT</code></td></tr>
<tr><td><b>13. Cookie</b></td><td>Cookie chuỗi</td><td>Trạng thái chuỗi cookie xác thực phiên đăng nhập.</td><td><code>Live</code> hoặc chuỗi rút gọn</td></tr>
<tr><td><b>14. $Earned</b></td><td>Thu nhập ước tính</td><td>Số tiền kiếm được từ Quỹ Sáng Tạo / TikTok Rewards ($).</td><td>USD ($)</td></tr>
<tr><td><b>15. $Balance</b></td><td>Số dư khả dụng</td><td>Số dư hiện có trong ví tài khoản có thể rút về ngân hàng ($).</td><td>USD ($)</td></tr>
<tr><td><b>16. CS</b></td><td>Chính Sách</td><td>Trạng thái tuân thủ chính sách kiếm tiền của kênh.</td><td>Bình thường / Cảnh báo</td></tr>
<tr><td><b>17. RPM</b></td><td>Doanh thu 1k view</td><td>Revenue Per Mille: Số tiền kiếm được trên mỗi 1.000 lượt xem hợp lệ.</td><td>USD ($)</td></tr>
<tr><td><b>18. QG</b></td><td>Quốc Gia</td><td>Vùng quốc gia tài khoản đăng ký (US, UK, FR, DE, VN...).</td><td>Mã quốc gia 2 chữ cái</td></tr>
<tr><td><b>19. KYC</b></td><td>Xác minh danh tính</td><td>Trạng thái xác thực thông tin cá nhân và giấy tờ tùy thân.</td><td><code>Yes</code> / <code>No</code></td></tr>
<tr><td><b>20. Note</b></td><td>Ghi chú</td><td>Ghi chú nội bộ dành cho người vận hành kênh.</td><td>Chuỗi văn bản</td></tr>
<tr><td><b>21. Re.Apply</b></td><td>Ngày nộp lại đơn</td><td>Ngày được phép gửi lại đơn xin tham gia Quỹ Sáng Tạo nếu bị loại.</td><td>Ngày tháng (DD-MM-YYYY)</td></tr>
<tr><td><b>22. PRIVACY</b></td><td>Quyền riêng tư</td><td>Chế độ hiển thị mặc định khi đăng video.</td><td><code>PUBLIC</code>, <code>FRIENDS</code>, <code>SELF</code></td></tr>
<tr><td><b>23. VAT</b></td><td>Khấu trừ thuế</td><td>Trạng thái kê khai thông tin thuế giá trị gia tăng.</td><td><code>Yes</code> / <code>No</code></td></tr>
<tr><td><b>24. TS</b></td><td>Thuế Hoa Kỳ</td><td>Trạng thái kê khai mẫu thuế W-8BEN cho thị trường Mỹ.</td><td><code>Yes</code> / <code>No</code></td></tr>
<tr><td><b>25. STT phụ</b></td><td>Thứ tự nhóm</td><td>Chỉ số thứ tự được đánh dấu riêng theo từng nhóm chiến dịch.</td><td>Số nguyên</td></tr>
<tr><td><b>26. VVP</b></td><td>Vi phạm chính sách</td><td>Số lượng cảnh báo hoặc gậy vi phạm tiêu chuẩn cộng đồng.</td><td>Số nguyên (0, 1, 2...)</td></tr>
<tr><td><b>27. MP</b></td><td>Marketplace</td><td>Trạng thái liên kết TikTok Creator Marketplace nhận booking tài trợ.</td><td><code>Yes</code> / <code>No</code></td></tr>
<tr><td><b>28. ID</b></td><td>Khóa CSDL</td><td>Mã định danh duy nhất trong cơ sở dữ liệu SQLite nội bộ.</td><td>Khóa chính (Primary Key)</td></tr>
</tbody>
</table>

<h2>Công Cụ Radar Kênh và Cảnh Báo View Thấp (Channel Radar):</h2>
<p>Hệ thống tích hợp công cụ phân tích dữ liệu chuyên sâu giúp tối ưu hóa nội dung và phát hiện sớm các vấn đề của kênh:</p>
<ul>
<li><b>Nhân khẩu học người xem (Audience Demographics):</b> Thống kê chi tiết tỉ lệ Nam / Nữ, phân bố độ tuổi (18-24, 25-34...) và các quốc gia người xem hàng đầu để tối ưu giá thầu RPM.</li>
<li><b>Khung giờ hoạt động cao điểm (Peak Active Hours):</b> Biểu đồ nhiệt hiển thị khung giờ người theo dõi online nhiều nhất trong ngày, làm căn cứ lên lịch đăng video chuẩn xác.</li>
<li><b>Cảnh báo tụt View / Flop:</b> Tự động phát hiện video có lượt xem bất thường dưới ngưỡng trung bình để người dùng kịp thời kiểm tra vi phạm hoặc điều chỉnh hashtag.</li>
</ul>
""",
    "proxy_security": """
<h1>CƠ CHẾ BẢO VỆ CHỐNG LEAK IP VÀ AN NINH AGENTSHIELD</h1>
<p>Dự án áp dụng tiêu chuẩn an ninh <b>AgentShield Tier-1 Security Architecture</b> nhằm bảo vệ toàn diện dữ liệu nhạy cảm và danh tính mạng:</p>

<h2>1. Windows DPAPI Hardware Credential Vault:</h2>
<ul>
<li>Mọi thông tin nhạy cảm bao gồm Access Token, Refresh Token, App Secret, Mật khẩu và Chuỗi Cookie tuyệt đối <b>KHÔNG</b> bao giờ lưu trữ dưới dạng văn bản thô (Plaintext).</li>
<li>Dữ liệu được mã hóa mức phần cứng bởi giao diện lập trình <b>Windows Data Protection API (DPAPI)</b> thông qua cặp hàm bảo mật <code>CryptProtectData</code> và <code>CryptUnprotectData</code>.</li>
<li>Khóa mã hóa gắn chặt với tài khoản người dùng đăng nhập Windows hiện tại, ngăn ngừa hoàn toàn nguy cơ bị trích xuất dữ liệu khi tệp CSDL bị sao chép sang máy tính khác.</li>
</ul>

<h2>2. Tường Lửa Ngăn Rò Rỉ IP (Network Leak Shield):</h2>
<ul>
<li><b>Chặn Rò Rỉ IP Trực Tiếp (Strict Proxy Gate):</b> Trước khi thực thi bất kỳ yêu cầu mạng nào (Đồng bộ số liệu, kiểm tra cookie, nạp video), hệ thống luôn kiểm tra tính sẵn sàng của proxy. Nếu proxy mất kết nối hoặc bị ngắt quãng, tác vụ lập tức dừng lại để bảo vệ tuyệt đối địa chỉ IP thật của máy trạm.</li>
<li><b>Chống Rò Rỉ WebRTC (WebRTC Leak Protection):</b> Trình duyệt Orbita Antidetect được cấu hình tắt hoàn toàn cơ chế quét STUN/TURN traversal thông qua các cờ khởi chạy chuyên dụng (<code>--disable-webrtc-hw-decoding</code>, <code>--webrtc-ip-handling-policy=disable_non_proxied_udp</code>).</li>
<li><b>Định Tuyến DNS An Toàn (DNS Leak Shield):</b> Toàn bộ yêu cầu phân giải tên miền (DNS Queries) được điều hướng đi qua cổng đường hầm của Proxy SOCKS5/HTTP, ngăn ngừa nhà cung cấp mạng nội địa phát hiện lưu lượng TikTok.</li>
</ul>

<h2>3. Quản Lý Proxy Pool và Kiểm Định Định Kỳ:</h2>
<p>Hệ thống hỗ trợ quản lý danh mục Proxy tập trung, tự động đo đạc tốc độ phản hồi (Ping), kiểm tra địa chỉ Geolocation và cảnh báo tức thời khi proxy có dấu hiệu chập chờn hoặc hết hạn băng thông.</p>
""",
    "upload_modes": """
<h1>3 PHƯƠNG THỨC UPLOAD TIKTOK TRI-MODAL VÀ COOKIE HYBRID</h1>
<p>Hệ thống tích hợp công nghệ độc quyền <b>SamMonny SDK Tri-Modal</b>, tự động lựa chọn phương thức tải lên tối ưu nhất cho từng loại tài khoản:</p>

<table>
<thead>
<tr>
<th>Phương Thức Upload</th>
<th>Nguyên Lý Kỹ Thuật</th>
<th>Ưu Điểm Vượt Trội</th>
<th>Mục Đích Sử Dụng</th>
</tr>
</thead>
<tbody>
<tr>
<td><b>1. Direct Post API (Chính thức)</b></td>
<td>Sử dụng giao thức chính thức TikTok for Developers qua endpoint <code>/v2/post/publish/video/init/</code>, phân mảnh video thành các chunk 10MB truyền song song.</td>
<td>Tốc độ tối đa, độ ổn định tuyệt đối, không tiêu tốn RAM trình duyệt, không lo checkpoint.</td>
<td>Kênh doanh nghiệp, kênh đối tác đã kích hoạt ứng dụng TikTok Developer.</td>
</tr>
<tr>
<td><b>2. Cookie API Hybrid (Khuyên dùng)</b></td>
<td>Stream video phân mảnh 5MB trực tiếp lên TikTok TOS CDN (S3 backend), sau đó dùng V8 Web Worker tạo chữ ký số <code>msToken</code> và <code>_signature</code> để xuất bản bài viết.</td>
<td>Tiết kiệm 95% RAM máy tính so với mở trình duyệt, hỗ trợ video dung lượng lớn, tốc độ đăng tức thì.</td>
<td>Kênh nuôi bằng Cookie, tài khoản chạy số lượng lớn cần tiết kiệm tài nguyên máy tính.</td>
</tr>
<tr>
<td><b>3. Orbita Headless Studio</b></td>
<td>Tự động hóa giao diện TikTok Creator Center thông qua Chrome DevTools Protocol (CDP), tự động gán proxy và cấu hình dấu vân tay trình duyệt.</td>
<td>Cho phép chọn nhạc bản quyền trực tiếp trên sàn Creator Studio, giải quyết các dạng CAPTCHA phức tạp.</td>
<td>Video reup cần chèn nhạc nền xu hướng, tài khoản bị hạn chế API hoặc cần gắn nhãn tài trợ.</td>
</tr>
</tbody>
</table>

<h2>Cơ Chế Vượt Joyride Onboarding Đa Ngôn Ngữ:</h2>
<p>Khi đăng video qua giao diện Creator Studio, TikTok thường hiển thị các hộp thoại hướng dẫn người dùng mới (Joyride Popups) làm gián đoạn tiến trình tự động. Trình điều khiển Orbita tích hợp bộ nhận diện và tự động đóng các hộp thoại này trên <b>5 ngôn ngữ</b> phổ biến:</p>
<ul>
<li><b>Tiếng Anh (EN):</b> Skip, Got it, Next, Done, Close.</li>
<li><b>Tây Ban Nha (ES):</b> Omitir, Entendido, Siguiente, Hecho, Cerrar.</li>
<li><b>Hàn Quốc (KO):</b> 건너뛰기, 확인, 다음, 완료, 닫기.</li>
<li><b>Nhật Bản (JA):</b> スキップ, 了解, 次へ, 完了, 閉じる.</li>
<li><b>Tiếng Việt (VI):</b> Bỏ qua, Đã hiểu, Tiếp theo, Hoàn tất, Đóng.</li>
</ul>

<h2>Khả Năng Phục Hồi và Tự Động Thử Lại (Exponential Backoff):</h2>
<p>Khi gặp sự cố nghẽn mạng hoặc lỗi tải lên tạm thời từ máy chủ TikTok, hệ thống tự động tạm dừng theo hàm mũ (2s, 4s, 8s, 16s...) và thử lại tối đa 3 lần trước khi đánh dấu lỗi, đảm bảo tỷ lệ hoàn thành tác vụ cao nhất.</p>
""",
    "appeals_monetization": """
<h1>NỘP KHÁNG CÁO VI PHẠM VÀ QUẢN TRỊ QUỸ SÁNG TẠO</h1>
<p>Hệ thống cung cấp các công cụ chuyên biệt giúp nhà sáng tạo bảo vệ quyền lợi kênh và tối đa hóa doanh thu MMO:</p>

<h2>1. Nộp Kháng Cáo Vi Phạm Video (SubmitAppealsV2):</h2>
<ul>
<li><b>Nhận diện vi phạm:</b> Khi video bị gắn cờ cảnh báo bản quyền âm thanh, hình ảnh hoặc vi phạm tiêu chuẩn cộng đồng, hệ thống sẽ cập nhật trạng thái trong cột <code>VVP</code>.</li>
<li><b>Gửi đơn kháng cáo tự động:</b> Cho phép gửi văn bản giải trình và bằng chứng sở hữu bản quyền trực tiếp lên hệ thống xét duyệt của TikTok thông qua API Creator ngầm.</li>
<li><b>Theo dõi kết quả:</b> Cập nhật tiến độ xử lý đơn kháng cáo theo 3 trạng thái: <i>Đang xét duyệt</i>, <i>Đã khôi phục video</i>, hoặc <i>Bác đơn kháng cáo</i>.</li>
</ul>

<h2>2. Quản Trị Đăng Ký Quỹ Sáng Tạo (Creator Rewards Program):</h2>
<ul>
<li><b>Theo dõi ngày đăng ký lại (Cột Re.Apply):</b> Đối với các kênh bị tạm dừng kiếm tiền hoặc bị từ chối đơn ban đầu, hệ thống hiển thị chính xác ngày được phép nộp lại đơn.</li>
<li><b>Đồng hồ đếm ngược:</b> Tự động tính toán số ngày còn lại đến thời điểm mở cổng đăng ký lại.</li>
<li><b>Nộp lại đơn tự động:</b> Khi đến hạn và kênh đạt đủ điều kiện (10.000 followers, 100.000 lượt xem trong 30 ngày), hệ thống hỗ trợ gửi yêu cầu nộp lại đơn chỉ với một cú nhấp chuột.</li>
</ul>

<h2>3. Tự Động Làm Mới Mã Xác Thực (OAuth Token Refresh):</h2>
<p>Mã truy cập API của TikTok có thời hạn sử dụng 24 giờ. Cơ chế tự động làm mới mã (Token Auto-Refresh) sẽ kiểm tra định kỳ và tự động gia hạn token trước khi hết hạn 72 giờ, đảm bảo các lịch đăng video tự động ban đêm không bao giờ bị đứt gãy.</p>
""",
    "backup_trash_ram": """
<h1>SAO LƯU DỮ LIỆU, THÙNG RÁC VÀ TỐI ƯU HÓA BỘ NHỚ RAM</h1>
<p>Bộ công cụ bảo trì và quản trị dữ liệu đảm bảo an toàn tuyệt đối cho tài sản kỹ thuật số của bạn:</p>

<h2>1. Sao Lưu và Chuyển Giao Dữ Liệu (Sync &amp; Transfer):</h2>
<ul>
<li><b>Đóng gói toàn diện:</b> Xuất toàn bộ CSDL Hồ sơ tài khoản, Danh mục Proxy và Cấu hình Dự án thành một tệp nén <code>.zip</code> duy nhất.</li>
<li><b>Mã hóa cấp độ quân sự:</b> Sử dụng thuật toán mã hóa <b>AES-256-GCM</b> kết hợp hàm sinh khóa bảo mật <b>Scrypt KDF</b> với mật khẩu tùy biến do người dùng thiết lập.</li>
<li><b>Di chuyển trạm làm việc:</b> Dễ dàng sao lưu định kỳ hoặc chuyển giao toàn bộ dữ liệu làm việc sang máy trạm mới mà không lo rò rỉ thông tin đăng nhập.</li>
</ul>

<h2>2. Thùng Rác và Phục Hồi Hồ Sơ (Trash Recovery):</h2>
<ul>
<li><b>Cơ chế Xóa mềm (Soft-delete):</b> Khi người dùng bấm xóa một hồ sơ tài khoản, dữ liệu không bị xóa vĩnh viễn khỏi ổ cứng mà được chuyển vào Thùng rác bảo vệ.</li>
<li><b>Phục hồi 1 chạm (Restore):</b> Cho phép kiểm tra danh sách tài khoản đã xóa và phục hồi nguyên vẹn dữ liệu (Cookie, Proxy, Thông số thống kê) trở lại bảng hoạt động bất cứ lúc nào.</li>
<li><b>Dọn sạch vĩnh viễn (Purge All):</b> Chỉ khi người dùng xác nhận dọn sạch trong Thùng rác, các bản ghi mới được loại bỏ hoàn toàn khỏi cơ sở dữ liệu.</li>
</ul>

<h2>3. Dọn Dẹp Trình Duyệt và Giải Phóng RAM Tức Thì:</h2>
<ul>
<li><b>Diệt tiến trình mồ côi (Zombie Process Cleanup):</b> Tự động quét và đóng các tiến trình Chromium / Orbita bị treo hoặc chạy ngầm không mong muốn, giải phóng ngay lập tức CPU và điện năng tiêu thụ.</li>
<li><b>Dọn sạch bộ nhớ đệm (Cache Purge):</b> Quét và xóa các tệp tạm thời không cần thiết (Media Cache, GPUCache, ShaderCache, Code Cache) nhằm thu hồi hàng trăm Megabytes đĩa cứng nhưng <b>bảo tồn 100% Cookie và phiên đăng nhập</b>.</li>
<li><b>Thu hồi RAM tức thì:</b> Kích hoạt hàm giải phóng bộ nhớ <code>EmptyWorkingSet</code> của Windows để thu hồi bộ nhớ RAM vật lý chưa giải phóng, giúp máy tính luôn mượt mà khi chạy lâu dài.</li>
</ul>
""",
    "license_shortcuts": """
<h1>BẢN QUYỀN HỆ THỐNG VÀ PHÍM TẮT TOÀN DIỆN</h1>
<p>Thông tin về cơ chế cấp phép bản quyền và các thao tác điều khiển tiện ích:</p>

<h2>1. Cơ Chế Bản Quyền Khóa Phần Cứng (Hardware Fingerprint):</h2>
<ul>
<li><b>Mã nhận dạng máy (Machine Code):</b> Được tổng hợp từ các thông số phần cứng duy nhất của máy tính bao gồm: Số sê-ri bộ vi xử lý (CPUID), Mã định danh bo mạch chủ (Mainboard UUID) và Địa chỉ card mạng chính (MAC Address).</li>
<li><b>Chữ ký điện tử Ed25519:</b> Khóa bản quyền được xác thực bằng mật mã học phi đối xứng hiện đại, đảm bảo tính toàn vẹn và chống làm giả tuyệt đối.</li>
</ul>

<h2>2. Bảng Phân Cấp Các Gói Bản Quyền:</h2>
<table>
<thead>
<tr>
<th>Gói Bản Quyền</th>
<th>Số Luồng Upload Tối Đa</th>
<th>Tính Năng Đi Kèm</th>
<th>Đối Tượng Phù Hợp</th>
</tr>
</thead>
<tbody>
<tr>
<td><b>Gói 1: Standard</b></td>
<td>Tối đa 3 luồng đồng thời</td>
<td>Upload API &amp; Trình duyệt cơ bản, Quản lý Proxy, Sao lưu CSDL.</td>
<td>Cá nhân mới bắt đầu làm quen với TikTok MMO.</td>
</tr>
<tr>
<td><b>Gói 2: Professional</b></td>
<td>Tối đa 10 luồng đồng thời</td>
<td>Mở khóa Cookie API Hybrid, Channel Radar, Đăng lịch so le có Jitter.</td>
<td>Nhóm làm nội dung chuyên nghiệp, quản trị 20 - 50 kênh.</td>
</tr>
<tr>
<td><b>Gói 3: Enterprise</b></td>
<td><span class="badge-green">KHÔNG GIỚI HẠN</span></td>
<td>Trọn bộ API ngầm, Kháng cáo vi phạm V2, Nộp lại đơn Quỹ Sáng Tạo, Hỗ trợ kỹ thuật 24/7.</td>
<td>Agency, Studio MMO quy mô lớn, vận hành hàng trăm tài khoản tự động.</td>
</tr>
</tbody>
</table>

<h2>3. Danh Mục Phím Tắt và Thao Tác Nhanh (Shortcuts):</h2>
<table>
<thead>
<tr>
<th>Tổ Hợp Phím</th>
<th>Thao Tác Thực Hiện</th>
<th>Mô Tả Chức Năng</th>
</tr>
</thead>
<tbody>
<tr><td><code>Ctrl + B</code></td><td>Thu gọn / Mở rộng bảng Video</td><td>Ẩn hoặc hiện bảng danh sách video để tối đa hóa không gian quản trị hồ sơ kênh.</td></tr>
<tr><td><code>Ctrl + F</code></td><td>Tìm kiếm nhanh</td><td>Di chuyển con trỏ chuột ngay lập tức vào ô tìm kiếm hồ sơ hoặc video.</td></tr>
<tr><td><code>Chuột Phải (Bảng Hồ Sơ)</code></td><td>Menu Ngữ Cảnh Hồ Sơ</td><td>Mở nhanh trình duyệt Orbita, Kiểm tra Cookie LIVE/DIE, Đổi trạng thái, Xóa vào Thùng rác.</td></tr>
<tr><td><code>Chuột Phải (Bảng Video)</code></td><td>Menu Ngữ Cảnh Video</td><td>Sửa tiêu đề/hashtag, Lên lịch đăng video riêng lẻ, Đăng ngay lập tức, Xóa video khỏi hàng đợi.</td></tr>
<tr><td><code>Nút Cài Đặt (Icon Bánh Răng)</code></td><td>Bảng Điều Khiển Trung Tâm</td><td>Truy cập nhanh toàn bộ chức năng: Dự án, Proxy, Cài đặt bảng, Sao lưu, Bản quyền, Hướng dẫn.</td></tr>
<tr><td><code>Tích chọn Dọn Dẹp Trước Khi Thoát</code></td><td>Tự Động Tối Ưu Khi Tắt</td><td>Tự động dọn dẹp cache rác và giải phóng RAM Chromium khi đóng ứng dụng.</td></tr>
</tbody>
</table>
""",
}


class UserGuideDialog(ReusableDialogMixin, QDialog):
    """
    Industrial-grade User Guide & Operational Runbook Dialog with multi-tab Markdown viewers.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hướng Dẫn Sử Dụng & Vận Hành Hệ Thống SonBetaPro")
        self.resize(880, 650)
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.HELP,
            title="Hướng Dẫn Sử Dụng & Vận Hành Hệ Thống",
            subtitle="Tài liệu vận hành, tra cứu 28 cột MMO, kỹ thuật chống leak proxy và quy trình upload an toàn.",
            parent=self,
        )
        layout.addWidget(header)

        self.tabs = style_tab_widget(QTabWidget(self))

        def make_tab(html_content: str) -> QWidget:
            tab = QWidget()
            t_layout = QVBoxLayout(tab)
            t_layout.setContentsMargins(6, 6, 6, 6)
            browser = QTextBrowser(tab)
            browser.document().setDefaultStyleSheet(INDUSTRIAL_GUIDE_CSS)
            browser.setHtml(html_content)
            browser.setOpenExternalLinks(True)
            t_layout.addWidget(browser)
            return tab

        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["quick_start"]), "Bắt Đầu Nhanh")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["mmo_columns"]), "28 Cột MMO")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["proxy_security"]), "Chống Leak Proxy")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["upload_modes"]), "3 Chế Độ Upload")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["appeals_monetization"]), "Radar và Kháng Cáo")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["backup_trash_ram"]), "Sao Lưu và RAM")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["license_shortcuts"]), "Bản Quyền và Phím Tắt")

        layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        btn_close = PushButton("Đã Hiểu && Đóng", self)
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
