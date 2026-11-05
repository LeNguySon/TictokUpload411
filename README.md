# TikTok Account & Video Manager (TAVM)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/UI-PyQt6%20%7C%20PyQt--Fluent--Widgets-success.svg)](https://qfluentwidgets.com/)
[![Database](https://img.shields.io/badge/database-SQLite%203.38%2B%20(24%20Tables)-blueviolet.svg)](https://sqlite.org/)
[![Security](https://img.shields.io/badge/Security-AgentShield%20%7C%20Windows%20Vault%20DPAPI-red.svg)](docs/05_security/security_and_compliance.md)
[![Architecture](https://img.shields.io/badge/Architecture-Clean%20Architecture%204--Tier-orange.svg)](docs/01_architecture/system_overview.md)
Ứng dụng desktop chuẩn công nghiệp dành cho Windows 11, chuyên biệt cho quản lý tài khoản TikTok số lượng lớn, theo dõi chỉ số tăng trưởng (Analytics) được ủy quyền và điều phối hàng đợi tải lên video (Upload Queue) tự động.
---
## 📑 Mục Lục Tài Liệu Kỹ Thuật (Documentation Map)
Hệ thống tài liệu được thiết kế theo chuẩn **Diátaxis Framework** kết hợp quy trình công nghiệp **ECC (Enterprise-grade Coding Companion)**:
| Phân Hệ Tài Liệu | Thư Mục / Liên Kết | Nội Dung Chi Tiết |
| :--- | :--- | :--- |
| **00. Tổng quan & Cốt lõi** | [PROJECT_SPEC.md](file:///d:/TictokUpload411/PROJECT_SPEC.md) | Bản đặc tả tổng thể hợp nhất và định hướng kỹ thuật toàn dự án |
| **01. Kiến trúc Hệ thống** | [docs/01_architecture/](file:///d:/TictokUpload411/docs/01_architecture/system_overview.md) | Clean Architecture 4 tầng, C4 diagrams, Thread Boundaries, ADRs |
| **02. Đặc tả Kỹ thuật** | [docs/02_specifications/](file:///d:/TictokUpload411/docs/02_specifications/) | Schema 24 bảng CSDL, UI/UX 28 cột Fluent, Phân nhóm Profile, Kho Proxy hàng loạt, SDK Tri-Modal |
| **03. Kế hoạch & Phân rã Tác vụ**| [docs/03_work_breakdown/](file:///d:/TictokUpload411/docs/03_work_breakdown/wbs_and_roadmap.md)| WBS, DAG, 20 Tasks chi tiết chia 5 Sprint với DoD và TDD specs |
| **04. Hướng dẫn & Vận hành** | [docs/04_guides/](file:///d:/TictokUpload411/docs/04_guides/development_setup.md) | Cài đặt môi trường phát triển, Quy trình kiểm định 6 Pha tự động |
| **05. An ninh & Bảo mật** | [docs/05_security/](file:///d:/TictokUpload411/docs/05_security/security_and_compliance.md) | Chuẩn AgentShield, Windows Credential Manager (DPAPI), Redaction Logging |
---
## 🏛️ Sơ Đồ Kiến Trúc Tổng Quan (Architecture Overview)
```mermaid
flowchart TB
    subgraph Presentation ["Presentation Layer (PyQt6 + Fluent Widgets)"]
        FW["FluentWindow / Shell"]
        AP["AccountsPage (TableView + Delegate)"]
        QP["UploadQueuePage (TableView + Delegate)"]
    end
    subgraph Application ["Application Layer (Services & Workers)"]
        AS["AccountService"]
        ANS["AnalyticsService"]
        UQS["UploadQueueService"]
        TP["QThreadPool (Bounded Concurrency)"]
        SW["TikTokSyncWorker (QRunnable)"]
        UW["VideoUploadWorker (QRunnable)"]
    end
    subgraph Domain ["Domain Layer (Logic & Policies)"]
        DM["Domain Models & Value Objects"]
        POL["Upload & Retry Policy (Exponential Backoff)"]
    end
    subgraph Infrastructure ["Infrastructure Layer (Storage & External SDK)"]
        REP["SQLite Repositories (Unit of Work)"]
        VLT["Windows Credential Vault (DPAPI)"]
        SDK["Sammonny SDK Adapter (Official Mode)"]
        LOG["Redaction Structured Logger"]
    end
    FW --> AP & QP
    AP & QP -->|User Actions / Signals| AS & ANS & UQS
    AS & ANS & UQS --> TP
    TP --> SW & UW
    SW & UW --> DM & POL
    SW & UW --> SDK
    SW & UW --> REP
    AS & ANS --> VLT
    REP --> DB[("SQLite DB (24 Tables)<br/>PRAGMA foreign_keys = ON")]
    SW & UW -->|Typed Signals| AP & QP
    SW & UW --> LOG
```
---
## ⚡ Bắt Đầu Nhanh (Quick Start)
### Yêu Cầu Tiên Quyết
- Hệ điều hành: **Windows 10 / 11 64-bit**
- Môi trường: **Python 3.11+**
- CSDL: SQLite 3.38+ (được tích hợp sẵn trong Python)
### Cài Đặt Môi Trường Phát Triển & Khởi Chạy
```powershell
# 1. Cài đặt các gói phụ thuộc
pip install -r requirements.txt
# 2. Chạy toàn bộ 39 bài test tự động (TDD)
python -m pytest tests/ -v
# 3. Kiểm tra chuẩn code PEP 8 (Zero errors)
python -m ruff check src tests main.py
# 4. Khởi chạy ứng dụng giao diện Fluent Windows 11
python main.py
```

> **SamMonny SDK** là thư viện nội bộ, không có trên PyPI. Bản wheel `sammonny-1.8.1` được đóng gói sẵn trong [`vendor/`](vendor/README.md); `requirements.txt` tự lấy từ đó qua `--find-links ./vendor`, vì vậy hãy chạy `pip` **từ thư mục gốc repo**.

---
## 🚦 Trạng Thái Dự Án (Project Status & Gateways)
- **Quy mô (Right-Sizing Tier):** **Tier 4 — Large** (Quy trình ECC khép kín).
- **Trạng thái hiện tại:** **Toàn bộ 5 Sprints đã hoàn thành xuất sắc**.
- **Tiến độ WBS:** **20/20 Tasks (100% Hoàn Thành)**.
  - [x] **Sprint 1 (Infrastructure & Storage)**: 24 bảng CSDL SQLite WAL mode, DPAPI Windows Credential Manager, Redaction Logging.
  - [x] **Sprint 2 (Domain & SamMonny Adapter)**: Domain Models (28 cột MMO), Chính sách chống rò rỉ IP (`NetworkLeakPolicy`), Tri-Modal SDK Adapter.
  - [x] **Sprint 3 (Concurrency & Threading)**: `AppSignalBus` Typed Signals, `QRunnable` Workers, singleton `ThreadPoolManager`.
  - [x] **Sprint 4 (Presentation Layer)**: Giao diện bảng kép Windows 11 Fluent UI (`QSplitter`), Bảng Profiles (28 cột MMO), Bảng Video Queue (`ProgressBar`), các Dialog quản lý.
  - [x] **Sprint 5 (End-to-End Hardening)**: Bulk Profile Parser Dialog, Trash Recycle Bin Dialog, Context Menu trên bảng, 39/39 tests passed.
- **Git Repository:** Đã đồng bộ 100% lên [https://github.com/LeNguySon/TictokUpload411](https://github.com/LeNguySon/TictokUpload411) trên nhánh `main`.
