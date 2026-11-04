# Đặc Tả Kỹ Thuật: Quản Lý Hàng Loạt Proxy & Sức Khỏe Mạng (Bulk Proxy Management)
## Phân Hệ: High-Throughput Proxy Subsystem (`TAVM-2026-WIN`)

Tài liệu này quy chuẩn toàn diện phân hệ quản lý kho proxy hàng loạt (từ vài chục đến hàng chục nghìn IP), cơ chế nạp thông minh, kiểm tra sức khỏe bất đồng bộ, chống rò rỉ IP thật và tự động điều phối gán vào profile.

---

## 1. Sơ Đồ Kiến Trúc Luồng Dữ Liệu Proxy (Dataflow Architecture)

```mermaid
flowchart TD
    RawInput["Dán Text / Tải File .TXT<br/>(Hàng loạt dòng Proxy)"] --> Parser["Smart Format Parser<br/>(Tự động nhận diện 5 định dạng)"]
    
    Parser --> Validated["Danh Sách Proxy Đã Chuẩn Hóa"]
    Validated --> DB[("SQLite DB (bảng proxies)<br/>Mật khẩu -> Windows Vault DPAPI")]
    
    DB <--> Checker["Async Health Checker Engine<br/>(Kiểm tra 500-1000 proxy / 15s)"]
    
    subgraph VerifyPipeline ["Quy Trình Kiểm Tra 4 Bước"]
        V1["1. TCP Handshake & Latency (Ping RTT)"] --> V2["2. Outbound IP Echo Request"]
        V2 --> V3{"3. So sánh Outbound IP == Local IP?"}
        V3 -- "Trùng IP thật" --> Leak["CRITICAL IP LEAK<br/>(Lập tức cách ly & vô hiệu hóa)"]
        V3 -- "Khác IP thật (An toàn)" --> V4["4. Offline GeoIP2 MMDB Lookup<br/>(<0.1ms: Quốc gia, Thành phố, ISP, Timezone)"]
    end
    
    Checker --> VerifyPipeline
    V4 --> Allocator["Proxy Allocation & Rotation Engine"]
    
    Allocator --> Mode1["Gán 1:1 Cố Định (Dedicated Profile Binding)"]
    Allocator --> Mode2["Điều Phối Pool Tự Động (Least-Connected Strategy)"]
    Allocator --> Mode3["Kích Hoạt Đổi IP 4G/Dcom (Webhook / Change IP URL)"]
    
    Mode1 & Mode2 --> Browser["Nạp Vào Trình Duyệt Orbita<br/>(Tiêm Preferences C++ Auth Bypass)"]
```

---

## 2. Nhận Diện & Nhập Hàng Loạt Thông Minh (Smart Format Parser)

Người dùng có thể dán danh sách hàng nghìn dòng từ Clipboard hoặc nạp file text. Bộ phân tích tự động chuẩn hóa các định dạng phổ biến nhất trên thị trường MMO:

| STT | Cú Pháp Định Dạng Đầu Vào | Ví Dụ Minh Họa | Ghi Chú Phân Tích |
| :---: | :--- | :--- | :--- |
| **1** | `host:port:username:password` | `103.145.2.10:8080:user99:pass123` | Định dạng chuẩn thông dụng nhất |
| **2** | `username:password@host:port` | `user99:pass123@103.145.2.10:8080` | Chuẩn URL authority |
| **3** | `protocol://user:pass@host:port` | `socks5://user99:pass123@103.145.2.10:1080` | Định dạng có giao thức rõ ràng |
| **4** | `host:port` | `45.76.12.5:9050` | Proxy mở hoặc Proxy whitelist IP |
| **5** | `host:port:user:pass:change_ip_url` | `1.2.3.4:8080:u:p:https://api.proxy.com/reset`| Proxy 4G có URL đổi IP |

### Logic Xử Lý & Loại Trừ Trùng Lặp (Deduplication):
- Ràng buộc duy nhất trên CSDL: `UNIQUE(host, port, username)`.
- Khi nhập trùng: Cập nhật mật khẩu và `change_ip_url` mới nhất, giữ nguyên lịch sử kiểm tra cũ nếu còn hạn.

---

## 3. Bộ Kiểm Tra Sức Khỏe Bất Đồng Bộ (Async Health Checker)

### 3.1. Hiệu Năng & Concurrency
- Sử dụng `asyncio` kết hợp `curl_cffi` (giả lập TLS 1.3 của Chrome 139) hoặc module [`sammonny.proxy.pool`](file:///D:/SamMonnygocLiengXiPoker/SamMonnygocLiengXiPoker/sdk/python/sammonny/proxy/pool.py).
- Kiểm tra song song **500 – 1,000 proxy cùng lúc trong vòng 10 – 15 giây** (không gây treo hay giật lag GUI).

### 3.2. Tiêu Chí Đánh Giá Trạng Thái & Ping RTT
1. **Nhanh (Fast / Alive)**: $RTT < 400\text{ms}$ (Huy hiệu xanh lá Fluent).
2. **Trung Bình (Normal)**: $400\text{ms} \le RTT \le 1200\text{ms}$ (Huy hiệu xanh dương).
3. **Chậm (Slow)**: $RTT > 1200\text{ms}$ (Huy hiệu vàng cam).
4. **Chết (Dead / Error)**: Timeout sau 5,000ms hoặc lỗi xác thực (Huy hiệu đỏ).

### 3.3. Cơ Chế Chống Rò Rỉ IP Thật (Critical IP Leak Protection)
> [!CAUTION]
> **Rủi ro lớn nhất trong nuôi nick TikTok:** Khi proxy bị sập hoặc cấu hình sai, request tự động rớt về IP thật của đường truyền gia đình/công ty. TikTok sẽ gắn cờ hàng loạt nick cùng 1 IP Việt Nam và khóa sạch toàn bộ dàn tài khoản (Mass Ban).
>
> **Giải pháp AgentShield:**
> 1. Bộ kiểm tra luôn ghi nhận `local_machine_ip`.
> 2. Mỗi lần kiểm tra proxy, nếu `outbound_ip == local_machine_ip`:
>    - Đánh dấu trạng thái **`LEAK_DETECTED`**.
>    - Lập tức ngắt và khóa không cho phép bất kỳ Profile nào sử dụng proxy này.
>    - Bật cờ `block_launch_on_dead_proxy = True` trên hệ thống.

---

## 4. Định Vị Địa Lý & Múi Giờ Cục Bộ (Zero-Network Offline GeoIP2)

Thay vì gọi API bên ngoài (dễ bị chặn rate-limit hoặc làm lộ IP proxy), hệ thống tích hợp trực tiếp cơ sở dữ liệu nhị phân MaxMind `GeoLite2-City.mmdb` và `GeoLite2-ASN.mmdb`:
- **Tốc độ tra cứu**: $< 0.1\text{ms}$ cho mỗi địa chỉ IP.
- **Tiêu tốn mạng**: **0 MB Network Overhead**.
- **Thông tin trích xuất tự động**:
  - Mã quốc gia ISO (`US`, `GB`, `FR`, `DE`, `VN`...).
  - Tên thành phố và tọa độ địa lý (Vĩ độ / Kinh độ).
  - Nhà mạng viễn thông (ISP: Comcast, AT&T, Viettel, VNPT...).
  - **Múi giờ chuẩn IANA (`timezone_id`)**: Tự động tiêm vào Profile tương ứng để đồng bộ đồng hồ JavaScript V8, `Intl.DateTimeFormat`, và WebGL Clock của Orbita Browser, đảm bảo chống phát hiện 100%.

---

## 5. Chiến Lược Gán & Điều Phối Proxy Vào Profile

### 5.1. Gán Cố Định 1:1 (Dedicated Binding)
- Mỗi Profile gắn chết với 1 Proxy tĩnh duy nhất.
- Khi mở profile, nếu proxy này ở trạng thái `DEAD`, hệ thống chặn mở trình duyệt và đưa ra thông báo cảnh báo để người dùng thay IP trước.

### 5.2. Điều Phối Pool Tự Động (Least-Connected Pool Strategy)
- Hỗ trợ gom hàng loạt proxy vào một Pool dùng chung.
- Khi khởi chạy profile, hệ thống tự động bốc proxy:
  1. Đang ở trạng thái `ALIVE` với độ trễ thấp nhất.
  2. Có số lượng profile đang chạy cùng ít nhất (`assigned_profiles_count` nhỏ nhất).

### 5.3. Xoay IP Tự Động Cho Proxy 4G / Dcom (IP Rotation Workflow)
1. Trước khi mở profile hoặc bắt đầu một video upload job:
   - Gửi request HTTP GET đến `change_ip_url`.
   - Kích hoạt thời gian chờ Cooldown (5 – 10 giây).
   - Gọi lại Health Checker để xác nhận IP mới đã xuất hiện và khác với IP cũ.
   - Tự động cập nhật `public_ip` và `timezone` mới vào Profile.

---

## 6. Cơ Chế Nạp Proxy Vào Trình Duyệt Orbita (Auth Bypass)

Chromium tiêu chuẩn **không hỗ trợ** truyền username/password qua cờ `--proxy-server`:
```bash
# SẼ BỊ LỖI: Chromium mở popup dialog hỏi mật khẩu
chrome.exe --proxy-server="http://user:pass@1.2.3.4:8080"
```

**Giải pháp công nghiệp tích hợp với Orbita Chromium**:
- Hệ thống ghi thông số proxy và credentials trực tiếp vào file cấu hình `Default/Preferences` của Profile:
  ```json
  {
    "gologin": {
      "proxy": {
        "mode": "http",
        "host": "103.145.2.10",
        "port": "8080",
        "username": "user99",
        "password": "secret_password",
        "autoProxyRegion": true
      }
    }
  }
  ```
- Orbita C++ Engine tự động bắt sự kiện `OnAuthRequired` ở tầng mạng lõi và điền credentials ngầm, **hoàn toàn không làm xuất hiện hộp thoại đăng nhập Chrome**.

---

## 7. Bảo Mật AgentShield Tier-1 Cho Mật Khẩu Proxy

- Bảng `proxies` trong SQLite chỉ lưu chuỗi danh định: `password = '__vault__'`.
- Mật khẩu thực tế được lưu vào **Windows Credential Manager / DPAPI** thông qua hàm:
  `vault.proxy_vault_key(host, port, username)`.
- Khi xuất báo cáo hoặc chia sẻ file CSDL `.db`, mật khẩu proxy không bao giờ bị trích xuất hoặc lộ ra ngoài.

---

## 8. Giao Diện Người Dùng Quản Trị Proxy Chuẩn Windows 11 Fluent

1. **Hộp Thoại Quản Lý Kho Proxy (`ProxyManagerDialog`)**:
   - Mở nhanh qua nút `Quản lý Proxy` trên thanh menu công cụ.
   - Bảng hiển thị danh sách Proxy với các cột: `Host`, `Port`, `Giao Thức`, `Trạng Thái (InfoBadge)`, `Ping (RTT)`, `Quốc Gia (Cờ + Mã)`, `ISP`, `Profile Đang Gán`, `Hành Động`.
2. **Khu Vực Nhập Nhanh Hàng Loạt (Bulk Import Area)**:
   - Khung `PlainTextEdit` bo góc Fluent hỗ trợ dán danh sách nhiều dòng.
   - Nút `Phân Tích & Nạp Nhanh` hiển thị số lượng dòng hợp lệ trước khi bấm Xác Nhận.
3. **Thanh Thao Tác Hàng Loạt (Bulk Actions Bar)**:
   - Nút `Kiểm Tra Toàn Bộ Proxy (Check All)`: Khởi chạy worker ngầm và hiển thị thanh `ProgressBar` chạy mượt mà.
   - Nút `Xóa Proxy Chết (Delete Dead)`: Dọn sạch các proxy hỏng.
   - Nút `Gán Tự Động Cho Các Profile Chưa Có Proxy`: Tự động phân bổ đều vào dàn tài khoản.

