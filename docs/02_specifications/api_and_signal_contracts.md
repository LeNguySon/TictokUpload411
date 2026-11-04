# Hợp Đồng Luồng Tín Hiệu & Dữ Liệu (Signal & Event Contracts)

Tài liệu này định nghĩa giao thức giao tiếp đa luồng giữa Application Workers và GUI Presentation Layer bằng **PyQt6 Signals/Slots** kết hợp cấu trúc dữ liệu bất biến **Python Dataclasses**.

---

## 1. Định Nghĩa Payload Dữ Liệu (Typed Payloads)

Toàn bộ payload phát đi từ worker bắt buộc sử dụng `@dataclass(frozen=True)` để đảm bảo tính bất biến (Thread Safety) khi truyền qua ranh giới giữa các luồng:

```python
"""
Path: application/signals/payload_types.py
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

@dataclass(frozen=True)
class SyncProgressPayload:
    """Tiến độ đồng bộ 1 profile cụ thể."""
    profile_id: int
    task_name: str
    percent: int
    message: str

@dataclass(frozen=True)
class SyncResultPayload:
    """Kết quả hoàn tất đồng bộ 1 profile."""
    profile_id: int
    success: bool
    status_text: str
    metrics: Dict[str, Any]
    error_message: Optional[str] = None

@dataclass(frozen=True)
class SyncBatchSummaryPayload:
    """Tổng kết phiên quét hàng loạt profiles."""
    total_requested: int
    total_success: int
    total_failed: int
    duration_seconds: float

@dataclass(frozen=True)
class UploadProgressPayload:
    """Tiến độ tải lên video phân đoạn (Chunked Upload)."""
    job_id: int
    profile_id: int
    bytes_sent: int
    total_bytes: int
    percent: int

@dataclass(frozen=True)
class UploadStatusPayload:
    """Cập nhật checkpoint của job upload."""
    job_id: int
    status: str          # 'pending', 'uploading', 'done', 'failed'
    checkpoint: str      # 'init', 'chunk_1', 'verifying', 'reconciling'
    details: str

@dataclass(frozen=True)
class UploadCompletedPayload:
    """Tải lên video và xuất bản thành công."""
    job_id: int
    publish_id: str
    tiktok_video_id: Optional[str]
    video_share_url: Optional[str]

@dataclass(frozen=True)
class UploadErrorPayload:
    """Lỗi trong quá trình upload."""
    job_id: int
    error_code: str
    redacted_message: str
    is_retryable: bool
    suggested_action: str
```

---

## 2. Trục Tín Hiệu Ứng Dụng (Central Signal Bus)

```python
"""
Path: application/signals/app_signals.py
"""
from PyQt6.QtCore import QObject, pyqtSignal
from application.signals.payload_types import (
    SyncProgressPayload,
    SyncResultPayload,
    SyncBatchSummaryPayload,
    UploadProgressPayload,
    UploadStatusPayload,
    UploadCompletedPayload,
    UploadErrorPayload,
)

class AppSignalBus(QObject):
    """Trục tín hiệu trung tâm (Singleton Bus)."""

    # --- NHÓM TÍN HIỆU ĐỒNG BỘ CHỈ SỐ & TÀI KHOẢN ---
    sig_sync_started = pyqtSignal(int)                         # total_profiles
    sig_sync_progress = pyqtSignal(SyncProgressPayload)        # tiến độ từng bước
    sig_sync_profile_done = pyqtSignal(SyncResultPayload)      # kết quả 1 profile
    sig_sync_batch_done = pyqtSignal(SyncBatchSummaryPayload)  # hoàn tất toàn bộ đợt

    # --- NHÓM TÍN HIỆU HÀNG ĐỢI TẢI LÊN VIDEO ---
    sig_upload_started = pyqtSignal(int)                       # job_id
    sig_upload_progress = pyqtSignal(UploadProgressPayload)    # tiến độ tải %
    sig_upload_checkpoint = pyqtSignal(UploadStatusPayload)    # checkpoint status
    sig_upload_finished = pyqtSignal(UploadCompletedPayload)   # hoàn tất thành công
    sig_upload_failed = pyqtSignal(UploadErrorPayload)         # lỗi tải lên
    sig_upload_cancelled = pyqtSignal(int)                     # job_id bị hủy an toàn

    # --- NHÓM TÍN HIỆU HỆ THỐNG & AN TOÀN ---
    sig_vault_locked = pyqtSignal(str)                         # cảnh báo lỗi DPAPI
    sig_quota_exceeded = pyqtSignal(int, str)                  # profile_id, cooldown_time
```

---

## 3. Bản Đồ Slot Consumer Trên Giao Diện (Slot Binding Map)

| Tín Hiệu Phát Đi | Widget / Consumer Tiếp Nhận | Hành Động Xử Lý Trên GUI |
| :--- | :--- | :--- |
| `sig_sync_progress` | `AccountsPage.table_view` | Cập nhật text trạng thái & icon xoay tại dòng của profile |
| `sig_sync_profile_done`| `AccountTableModel` | Cập nhật lại các cột `views_month`, `followers`, `likes` |
| `sig_sync_batch_done` | `MainWindow.status_bar` & `InfoBar`| Ẩn ProgressRing, hiện thông báo *"Đã đồng bộ xong X/Y profile"* |
| `sig_upload_progress` | `QueueTableModel` | Cập nhật giá trị cột ProgressBar nội tuyến của job tương ứng |
| `sig_upload_checkpoint`| `QueueTableModel` | Thay đổi nhãn badge: `Init` $\rightarrow$ `Uploading` $\rightarrow$ `Verifying` |
| `sig_upload_finished` | `QueueTableModel` & `InfoBar` | Chuyển badge sang `Done`, gắn link `video_id`, hiện thông báo |
| `sig_upload_failed` | `UploadQueuePage` | Đổi badge sang `Failed`, hiển thị popup gợi ý hướng xử lý |

