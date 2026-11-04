# Giao Thức Tích Hợp Toàn Diện SamMonny SDK (Full Capability Integration Protocol)

Tài liệu này quy chuẩn việc tích hợp giữa tầng ứng dụng `TictokUpload411` và gói thư viện **`sammonny` Python SDK (v1.2.0 / 1.8.1)** (đặt tại `D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\sdk\python`).

Hệ thống **tái sử dụng hoàn toàn 100% tất cả chức năng** do SDK cung cấp: từ phân phối video đa chế độ (Tri-Modal), động cơ ký mật mã ByteDance siêu tốc (>21,000 sig/s), bộ phát HTTP cấp nhân Chromium (In-Kernel Egress chống lộ JA3/JA4), cắt lát video, giải captcha đến kiểm soát và giải phóng 99% RAM.

---

## 1. Danh Mục Biểu Tượng SDK Tái Sử Dụng (Public Symbols & Architecture)

Hệ thống kết nối trực tiếp với các module cốt lõi của `sammonny`:

```python
"""
Path: src/infrastructure/tiktok/sammonny_adapter.py
"""
# 1. Pipeline phân phối video đa chế độ (Tri-Modal Publishing)
from sammonny.platforms.tiktok import (
    TikTokPublisherAdapter,
    TikTokDirectPostClient,
    TikTokHybridApiUploader,
    TikTokHeadlessStudioUploader,
    TikTokPipeline,
    UploadMode,
    RemoteStatus,
    CapabilityResult,
    DraftResult,
    UploadResult,
)

# 2. Điều khiển nhân trình duyệt Antidetect & Quản lý phiên
from sammonny.engine.core import AntidetectEngine
from sammonny.engine.session import AntidetectSession

# 3. Động cơ ký mật mã ByteDance siêu tốc
from sammonny.signatures.harvester import KernelSignatureHarvester
from sammonny.signatures.kernel_live import CDPLiveSigner

# 4. Tối ưu hóa bộ nhớ & Quản trị tài nguyên
from sammonny.memory.manager import MemoryManager

# 5. Quản trị Proxy Pool & Kiểm toán rò rỉ mạng
from sammonny.proxy.pool import ProxyPool
from sammonny.proxy.parser import parse_proxy
from sammonny.network.leak_auditor import NetworkLeakAuditor
```

---

## 2. Đặc Tả 3 Chế Độ Xuất Bản Video (Tri-Modal Publishing Specification)

Hệ thống hỗ trợ 3 chế độ vận hành linh hoạt thông qua [`TikTokPublisherAdapter`](file:///D:/SamMonnygocLiengXiPoker/SamMonnygocLiengXiPoker/sdk/python/sammonny/platforms/tiktok.py#L638-L890):

### 2.1. Chế Độ 1: `OFFICIAL_DIRECT_POST` (TikTok Content Posting API v2)
- **Áp dụng cho**: Kênh có Access Token ủy quyền chính thức (OAuth Bearer).
- **Quy trình thực thi**:
  1. `direct_client.query_creator_info(access_token)`: Kiểm tra tính hợp lệ và quyền riêng tư được phép.
  2. `direct_client.init_direct_post(...)`: Khởi tạo phiên đăng tại `/v2/post/publish/video/init/`, nhận `upload_url` và `publish_id`.
  3. `direct_client.upload_video_chunks(...)`: Truyền tải các chunk theo chuẩn ByteDance TOS (HTTP PUT với `Content-Range`, exponential backoff retry).
  4. `direct_client.get_post_status(...)`: Đối soát trạng thái xuất bản bất đồng bộ (`PUBLISH_COMPLETE`, `PROCESSING_UPLOAD`, `FAILED`).

### 2.2. Chế Độ 2: `COOKIE_API_HYBRID` (TOS Chunk Streaming + In-Kernel V8 Fetch Injection)
- **Áp dụng cho**: Kênh đăng nhập bằng Cookie/Profile Orbita, cần tốc độ cao và tiết kiệm RAM tối đa.
- **Quy trình 3 pha kế thừa từ `Gloglin2609`**:
  - **Pha 1 (`upload.begin`)**: Gọi API lấy endpoint TOS CDN và STS credentials.
  - **Pha 2 (TOS Streaming)**: Truyền tải trực tiếp các chunk video 5MB qua HTTP (tiết kiệm **95% RAM** so với upload qua DOM).
  - **Pha 3 (`upload.publish`)**: Tiêm `window.fetch()` trực tiếp trong ngữ cảnh V8 JavaScript của Orbita Chromium qua CDP (`CDPLiveSigner`). Tận dụng chữ ký runtime sống của trình duyệt, vượt qua hoàn toàn WAF acrawler mà không bị lỗi 403 Forbidden.
  - **Tự động dự phòng (Auto-Fallback)**: Tự động chuyển tiếp sang Chế độ 3 (`HEADLESS_STUDIO`) nếu gặp puzzle hoặc yêu cầu giải captcha.

### 2.3. Chế Độ 3: `HEADLESS_STUDIO` (Orbita Browser Automation)
- **Áp dụng cho**: Trường hợp kênh bị giới hạn API hoặc cần thao tác trực tiếp trên giao diện TikTok Studio.
- **Quy trình thực thi**:
  1. Mở profile Orbita chạy ngầm (`headless=True`).
  2. Điều hướng đến `https://www.tiktok.com/creator-center/upload`.
  3. Nạp file qua CDP DOM `setFileInputFiles` (tránh dialog file của hệ điều hành).
  4. Điền caption và chọn quyền riêng tư bằng nhịp sinh học người thật (WPM 85).
  5. Bấm nút `Post` bằng thuật toán động học tự nhiên **Minimum Jerk / WindMouse**.

---

## 3. Đặc Tả Động Cơ Chữ Ký Mật Mã (ByteDance Cryptographic Harvester)

Tái sử dụng trực tiếp lớp [`KernelSignatureHarvester`](file:///D:/SamMonnygocLiengXiPoker/SamMonnygocLiengXiPoker/sdk/python/sammonny/signatures/harvester.py):

| Thuật Toán | Bản Chất Kỹ Thuật | Phạm Vi Ứng Dụng |
| :--- | :--- | :--- |
| **`X-Gorgon`** | S-Box 256 hoán vị, rolling bit shifts, tiền tố `8404` | Ký xác thực luồng VOD, Aweme API, Upload TOS |
| **`X-Bogus`** | Double MD5 băm với bảng mã ByteDance 64 ký tự | Ký xác thực các endpoint Web tiêu chuẩn |
| **`a_bogus`** | acrawler v3 tích hợp thông số Canvas, CPU, RAM, clock | Chữ ký WAF thế hệ mới chống bot & giả lập |
| **`msToken`** | Chuỗi entropy cao sinh theo phiên làm việc | Định danh thiết bị và phiên phần cứng |
| **`store-idc`** | Phân giải IDC Geo-Affinity (`alisg`, `useast2a`, `eucentral`) | Đồng bộ cụm máy chủ khu vực tránh cờ rủi ro IP |
| **`sign_mobile`** | Header mobile Metasec (`X-Gorgon`, `X-Argus`, `X-Ladon`, `X-Khronos`) | Giả lập request từ ứng dụng TikTok di động (Box Phone) |
| **`ttencrypt_payload`**| Magic header `746305100000` + Gzip + S-box | Mã hóa gói tin body bảo mật của ByteDance |

---

## 4. Đặc Tả Bộ Phát HTTP Cấp Nhân (In-Kernel HTTP Egress Client)

Để chống lộ vân tay mạng (JA3/JA4 TLS Fingerprint và HTTP/2 settings do OpenSSL của Python tạo ra):
- Tầng mạng sử dụng `session.http` hoặc `engine.http_request(profile_id, ...)`:
  - Gói tin được phát trực tiếp từ **nhân C++ Chromium của Orbita**.
  - Bắt tay TLS 1.3 thực hiện bởi **BoringSSL** của Chrome 139.
  - Khung HTTP/2 tạo bởi `net::SpdySession` của Chromium.
  - Tự động đính kèm Client Hints và chữ ký ByteDance (`sign_bytedance=True`).

---

## 5. Cắt Lát Video & Tối Ưu Hóa Bộ Nhớ RAM

1. **Cắt lát video theo khoảng lặng âm thanh**:
   - `pipeline.calculate_video_slices(video_path, max_duration_sec=60.0)`: Tự động phân tích điểm im lặng của audio để cắt video 9:16 tối ưu cho TikTok Shorts/Reels mà không bị ngắt quãng câu từ.
2. **Giải phóng 99% RAM sau mỗi lần upload**:
   - `MemoryManager.trim_working_set(process_id)`: Sau khi hoàn tất mỗi luồng upload hoặc mở trình duyệt, hệ thống gọi lệnh giải phóng RAM của Chromium về mức nền, cho phép ứng dụng mở hàng chục profile đồng thời trên máy tính 8GB/16GB RAM mà không bị tràn bộ nhớ.
