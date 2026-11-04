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
    PushButton,
)

USER_GUIDE_CONTENT = {
    "quick_start": """
# 🚀 HƯỚNG DẪN BẮT ĐẦU NHANH (QUICK START)

Chào mừng bạn đến với **TikTok Manager (TAVM-2026-WIN)** — Hệ thống quản trị và đăng tải video TikTok đa luồng chuẩn Windows 11 Fluent UI!

### Quy trình 4 bước chuẩn hóa:
1. **Khởi tạo Dự án & Nhóm**:
   - Mở menu **⚙ Cài Đặt** > **Quản lý Dự án / Chiến dịch**.
   - Tạo các nhóm dự án như: *Reup US*, *Affiliate Beta*, *Kênh Bán Hàng*.
2. **Nạp Proxy Chống Bị Khóa Kênh**:
   - Mở menu **⚙ Cài Đặt** > **Công cụ Proxy & Leak Audit**.
   - Dán proxy định dạng `host:port:user:pass` hoặc `host:port`.
   - Hệ thống tự động kiểm tra Ping, Quốc gia, và kích hoạt tường lửa chống rò rỉ IP (Network Leak Shield).
3. **Thêm Tài Khoản (Profiles)**:
   - Dùng **Add 1 profile** hoặc **Add nhiều profile (Hàng loạt)**.
   - Hỗ trợ cú pháp phân tách bằng gạch đứng: `Tên|Email|Mật khẩu|Cookie|Proxy`.
4. **Nạp Video & Lên Lịch Tự Động**:
   - Bấm **💻 Thêm Video (Máy tính)** để chọn hàng loạt video `.mp4`.
   - Bấm **📅 Lên lịch** để phân bổ thời gian đăng so le (staggered) kèm độ lệch ngẫu nhiên (Jitter) nhằm tránh thuật toán spam của TikTok.
   - Chọn tài khoản trên bảng và bấm **🚀 Bắt đầu Upload**!
""",
    "mmo_columns": """
# 📊 GIẢI THÍCH CHI TIẾT 28 CỘT MMO (TIKTOK METRICS)

Bảng hồ sơ được thiết kế theo đúng chuẩn SSMATool Parity với 28 trường số liệu chuyên sâu:

| Cột | Tên Tiếng Việt | Ý Nghĩa Chuyên Sâu |
|---|---|---|
| **0. STT** | Số thứ tự | Chỉ số thứ tự hàng trong danh sách. |
| **1. Avt** | Ảnh đại diện | Icon hiển thị trạng thái avatar tài khoản. |
| **2. Tên hồ sơ** | Tên Profile | Tên định danh hồ sơ trong hệ thống máy tính. |
| **3. Logged** | Đăng nhập | Trạng thái đăng nhập (Có cookie hoặc token hợp lệ). |
| **4. Proxy** | Địa chỉ IP | Proxy được gán tĩnh cho hồ sơ (`IP:Port`). |
| **5. Type** | Loại Proxy | Loại giao thức kết nối (`HTTP`, `SOCKS5`). |
| **6. ID Tiktok** | TikTok Handle | Nickname / User ID chính thức trên TikTok (`@username`). |
| **7. Views(30d)** | Lượt xem 30 ngày | Tổng lượt xem video trong 30 ngày gần nhất (K / M views). |
| **8. T.Follows** | Tổng Follower | Tổng số lượng người theo dõi kênh. |
| **9. T.Views** | Tổng Lượt Xem | Tổng lượt xem toàn kênh từ khi khởi tạo. |
| **10. T.Video** | Tổng Số Video | Số lượng video đã được đăng tải trên kênh. |
| **11. Email** | Hộp thư | Email đăng ký hoặc email khôi phục của tài khoản. |
| **12. Tình trạng** | Trạng thái | `LIVE`, `DIE`, `CHECKPOINT`, hoặc `stopped`. |
| **13. Cookie** | Cookie chuỗi | Trạng thái chuỗi cookie (`Live` hoặc chuỗi rút gọn). |
| **14. $Earned** | Thu nhập ước tính | Số tiền đã kiếm được từ Quỹ Sáng Tạo / Beta Program ($). |
| **15. $Balance** | Số dư khả dụng | Số dư hiện có trong ví tài khoản có thể rút ($). |
| **16. CS** | Chính Sách | Trạng thái tuân thủ chính sách kiếm tiền. |
| **17. RPM** | Doanh thu 1k view | Revenue Per Mille (Số tiền kiếm được trên 1.000 lượt xem hợp lệ). |
| **18. QG** | Quốc Gia | Vùng quốc gia tài khoản đăng ký (`US`, `UK`, `FR`, `DE`, `VN`...). |
| **19. KYC** | Xác minh danh tính | Trạng thái xác thực danh tính thuế / giấy tờ (`Yes` / `No`). |
| **20. Note** | Ghi chú | Ghi chú nội bộ dành cho người vận hành. |
| **21. Re.Apply** | Ngày đăng ký lại | Ngày được phép gửi lại đơn kiếm tiền nếu bị từ chối. |
| **22. PRIVACY** | Quyền riêng tư | Chế độ mặc định khi đăng tải video (`PUBLIC`, `FRIENDS`, `SELF`). |
| **23. VAT** | Khấu trừ thuế | Trạng thái thông tin thuế giá trị gia tăng. |
| **24. TS** | Thuế Hoa Kỳ | Trạng thái kê khai thông tin thuế W-8BEN. |
| **25. STT phụ** | Số thứ tự nhóm | Thứ tự được đánh dấu theo nhóm chiến dịch. |
| **26. VVP** | Vi phạm chính sách | Số gậy hoặc cảnh báo vi phạm tiêu chuẩn cộng đồng. |
| **27. MP** | Marketplace | Trạng thái liên kết TikTok Creator Marketplace. |
| **28. ID** | Khóa CSDL | ID định danh duy nhất trong SQLite nội bộ. |
""",
    "proxy_security": """
# 🛡️ CƠ CHẾ BẢO VỆ CHỐNG LEAK & BẢO MẬT CREDENTIAL

Dự án áp dụng tiêu chuẩn **AgentShield Tier-1 Security Architecture**:

### 1. Windows DPAPI Credential Vault
- Toàn bộ Access Token, Refresh Token, App Secret và Cookie phiên đăng nhập tuyệt đối **KHÔNG** lưu ở dạng Plaintext.
- Dữ liệu được mã hóa mức phần cứng bởi **Windows Data Protection API (DPAPI)** thông qua `CryptProtectData` và `CryptUnprotectData`.
- Khóa mã hóa gắn chặt với tài khoản người dùng đăng nhập Windows hiện tại.

### 2. Tường Lửa Ngăn Rò Rỉ IP (Network Leak Policy)
- **Direct IP Leak**: Kiểm tra proxy trước khi gọi bất kỳ API nào; nếu proxy lỗi hoặc mất kết nối, hệ thống lập tức ngắt phiên làm việc để không bao giờ lộ IP thật của máy chủ / máy trạm tại Việt Nam.
- **WebRTC Leak Shield**: Trình duyệt Orbita Antidetect được cấu hình tắt hoàn toàn WebRTC STUN/TURN traversal (`--disable-webrtc-hw-decoding`, `--webrtc-ip-handling-policy=disable_non_proxied_udp`).
- **DNS Leak Shield**: Mọi truy vấn phân giải tên miền đều được định tuyến đi qua cổng tunnel của proxy socks5/http.
""",
    "upload_modes": """
# ⚡ 3 PHƯƠNG THỨC UPLOAD TIKTOK TRI-MODAL

Hệ thống tích hợp công nghệ **SamMonny SDK Tri-Modal** tự động phân loại video:

1. **Phương Thức 1: Direct Post API (Chính thức)**
   - Phù hợp: Video dung lượng chuẩn, kênh đã liên kết TikTok for Developers.
   - Cơ chế: Gửi thông qua endpoint `https://open.tiktokapis.com/v2/post/publish/video/init/` với chunk upload 10MB song song.
   - Ưu điểm: Tốc độ cao nhất, ổn định tuyệt đối, không lo checkpoint browser.

2. **Phương Thức 2: Cookie Hybrid TOS (Chunk 5MB)**
   - Phù hợp: Kênh nuôi bằng Cookie, video dung lượng trung bình.
   - Cơ chế: Tự động giả lập chữ ký `msToken`, `X-Bogus`, `_signature` và đẩy chunk 5MB trực tiếp lên TikTok TOS CDN.
   - Ưu điểm: Không cần mở trình duyệt đồ họa, tiết kiệm 95% RAM máy tính.

3. **Phương Thức 3: Orbita Headless Studio**
   - Phù hợp: Video có bản quyền âm thanh cần chọn nhạc trên sàn TikTok Studio, hoặc video cần bypass CAPTCHA phức tạp.
   - Cơ chế: Điều khiển Orbita Antidetect qua CDP, tự động gán proxy, tải video lên Creator Center và bấm xuất bản.
""",
    "shortcuts": """
# ⌨️ PHÍM TẮT & THAO TÁC NHANH (SHORTCUTS)

- **Ctrl + F**: Nhảy vào ô tìm kiếm hồ sơ hoặc ô tìm kiếm video.
- **Chuột Phải (Context Menu)**:
  - Trên bảng hồ sơ: Mở nhanh Orbita Antidetect, kiểm tra cookie LIVE/DIE, đổi trạng thái, xóa vào thùng rác.
  - Trên bảng video: Chỉnh sửa tiêu đề/hashtag, lên lịch đăng lẻ, tải lên ngay, xóa hàng.
- **Nút ⚙ Icon Cài Đặt**: Chứa toàn bộ trung tâm điều hành: Quản lý dự án, Proxy, Cài đặt bảng, Sao lưu/Khôi phục, Cấp quyền API.
- **Dọn Dẹp Trước Khi Thoát**: Đảm bảo tích chọn ở góc dưới bên phải để hệ thống tự động giải phóng bộ nhớ RAM Chromium khi đóng tool.
""",
}


class UserGuideDialog(QDialog):
    """
    Industrial-grade User Guide & Operational Runbook Dialog with multi-tab Markdown viewers.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📖 Hướng Dẫn Sử Dụng & Vận Hành Hệ Thống TikTok Manager")
        self.resize(800, 600)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.tabs = QTabWidget(self)

        def make_tab(markdown_text: str) -> QWidget:
            tab = QWidget()
            t_layout = QVBoxLayout(tab)
            t_layout.setContentsMargins(6, 6, 6, 6)
            browser = QTextBrowser(tab)
            browser.setMarkdown(markdown_text)
            browser.setOpenExternalLinks(True)
            t_layout.addWidget(browser)
            return tab

        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["quick_start"]), "🚀 Bắt Đầu Nhanh")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["mmo_columns"]), "📊 28 Cột MMO")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["proxy_security"]), "🛡️ Chống Leak Proxy")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["upload_modes"]), "⚡ 3 Chế Độ Upload")
        self.tabs.addTab(make_tab(USER_GUIDE_CONTENT["shortcuts"]), "⌨️ Phím Tắt")

        layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        btn_close = PushButton("Đã Hiểu & Đóng", self)
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
