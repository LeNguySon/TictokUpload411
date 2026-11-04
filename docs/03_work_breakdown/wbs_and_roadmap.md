# Kế Hoạch Triển Khai & Đồ Thị Phụ Thuộc Tác Vụ (WBS & Roadmap)

Tài liệu này tổng hợp cấu trúc phân rã công việc (**Work Breakdown Structure - WBS**), đồ thị phụ thuộc tác vụ (**Directed Acyclic Graph - DAG**), và lộ trình triển khai 5 Sprint chuẩn công nghiệp.

---

## 1. Đồ Thị Phụ Thuộc Tác Vụ (WBS DAG Diagram)

```mermaid
flowchart TD
    subgraph S1 ["Sprint 1: Hạ Tầng, CSDL & Security Vault"]
        T01["TSK-01-ENV<br/>Skeleton & Toolchain"]
        T02["TSK-02-MIG<br/>24 Tables SQLite Migration"]
        T03["TSK-03-REPO<br/>Repositories & Transactions"]
        T04["TSK-04-VAULT<br/>Windows DPAPI Vault"]
        T05["TSK-05-SEC-LOG<br/>Redaction Structured Logging"]
    end

    subgraph S2 ["Sprint 2: SDK Adapter & Domain Engine"]
        T06["TSK-06-SDK<br/>SamMonny Official Adapter"]
        T07["TSK-07-ACC-SVC<br/>Account Management Service"]
        T08["TSK-08-STATS-SVC<br/>Analytics & Provenance Service"]
        T09["TSK-09-QUEUE-SVC<br/>Upload Queue & Reconcile"]
    end

    subgraph S3 ["Sprint 3: Concurrency Engine & Multi-threading"]
        T10["TSK-10-WORKER-BASE<br/>QRunnable & Signal Bus"]
        T11["TSK-11-SYNC-WORKER<br/>Bounded TikTokSyncWorker"]
        T12["TSK-12-UPLOAD-WORKER<br/>VideoUploadWorker & Chunking"]
    end

    subgraph S4 ["Sprint 4: Windows 11 Fluent UI Presentation"]
        T13["TSK-13-UI-SHELL<br/>FluentWindow & Navigation"]
        T14["TSK-14-UI-ACC-PAGE<br/>AccountsPage & TableModel"]
        T15["TSK-15-UI-QUEUE-PAGE<br/>UploadQueuePage & Progress Ring"]
        T16["TSK-16-UI-DIALOGS<br/>Dialogs: Add, Import, Video Config"]
    end

    subgraph S5 ["Sprint 5: Tích Hợp Toàn Trình, Kiểm Thử & Phát Hành"]
        T17["TSK-17-INT-E2E<br/>End-to-End Integration Tests"]
        T18["TSK-18-PERF<br/>Kiểm Thử Tải & Table Virtualization"]
        T19["TSK-19-AUDIT<br/>AgentShield Security Audit"]
        T20["TSK-20-RELEASE<br/>Đóng Gói PyInstaller & Runbook"]
    end

    T01 --> T02 --> T03
    T01 --> T04
    T01 --> T05
    T03 & T04 --> T06
    T03 & T06 --> T07 & T08 & T09
    T05 & T07 & T08 & T09 --> T10
    T10 --> T11 & T12
    T01 --> T13
    T10 & T13 --> T14 & T15 & T16
    T11 & T12 & T14 & T15 & T16 --> T17
    T17 --> T18 --> T19 --> T20
```

---

## 2. Bảng Tổng Hợp 5 Sprint & Ma Trận Phân Bổ

| Sprint | Gói Công Việc (Epic) | Danh Sách Task | Sản Phẩm Bàn Giao Cốt Lõi |
| :--- | :--- | :--- | :--- |
| **Sprint 1** | Hạ Tầng, CSDL & Vault | `TSK-01` $\rightarrow$ `TSK-05` | CSDL 24 bảng sẵn sàng, DPAPI Vault, Logger khử nhạy cảm |
| **Sprint 2** | SDK & Nghiệp Vụ Cốt Lõi | `TSK-06` $\rightarrow$ `TSK-09` | Adapter SamMonny Official, Services Quản lý Acc, Stats, Queue |
| **Sprint 3** | Đa Luồng & Bất Đồng Bộ | `TSK-10` $\rightarrow$ `TSK-12` | Bounded ThreadPool, Worker đồng bộ, Worker upload chunking |
| **Sprint 4** | Giao Diện Windows 11 Fluent | `TSK-13` $\rightarrow$ `TSK-16` | Bảng kép, Models ảo hóa, Delegates hiển thị, Hệ thống Dialogs |
| **Sprint 5** | Tích Hợp, Tải & Đóng Gói | `TSK-17` $\rightarrow$ `TSK-20` | Test E2E, Kiểm thử 5000 profiles, Security Audit, File `.exe` |

---

## 3. Quy Ước Nghiệm Thu Tác Vụ (Definition of Done - DoD)

Mọi task kỹ thuật chỉ được xem là hoàn thành khi đáp ứng đủ 5 điều kiện:
1. **Mã nguồn hoàn chỉnh**: Có Type hints đầy đủ (`mypy --strict` pass).
2. **Kiểm thử tự động (TDD)**: Có ít nhất một unit test kiểm tra luồng chính (Happy Path) và một test kiểm tra ngoại lệ (Error Path).
3. **Tuân thủ chuẩn code**: Không có cảnh báo từ `ruff check .`.
4. **Không rò rỉ bí mật**: Không commit bất kỳ token, password hoặc file database thật nào vào repository.
5. **Cập nhật tài liệu**: Đánh dấu hoàn thành trên WBS và ghi nhật ký thay đổi.

