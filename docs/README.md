# Trung Tâm Tài Liệu Kỹ Thuật (Technical Documentation Center)

Chào mừng bạn đến với kho tài liệu kỹ thuật toàn diện của dự án **TikTok Account & Video Manager (TAVM)**. Hệ thống tài liệu được tổ chức theo tiêu chuẩn công nghiệp và cấu trúc **Diátaxis Framework**:

```
docs/
├── 01_architecture/              # Kiến trúc hệ thống, C4 model, ADRs (Explanation)
│   ├── system_overview.md        # Tổng quan kiến trúc Clean Architecture 4 tầng
│   └── adr/                      # Architecture Decision Records
│       ├── 0001-ui-framework-selection.md
│       ├── 0002-database-preservation.md
│       ├── 0003-secrets-management-vault.md
│       ├── 0004-async-worker-thread-model.md
│       └── 0005-official-sdk-mode.md
├── 02_specifications/            # Đặc tả kỹ thuật, schemas, hợp đồng (Reference)
│   ├── ui_ux_specification.md    # Đặc tả giao diện Windows 11 Fluent UI
│   ├── database_schema.md        # Danh mục 24 bảng CSDL SQLite kế thừa
│   ├── api_and_signal_contracts.md # Hợp đồng tín hiệu đa luồng Qt
│   └── sdk_integration_protocol.md # Hợp đồng tích hợp SamMonny SDK
├── 03_work_breakdown/            # Kế hoạch thực thi, WBS & Tasks (Applied)
│   ├── wbs_and_roadmap.md        # Đồ thị DAG & Tổng quan 5 Epics
│   ├── sprint_01_core_infrastructure.md
│   ├── sprint_02_sdk_and_domain.md
│   ├── sprint_03_concurrency_workers.md
│   ├── sprint_04_fluent_ui_presentation.md
│   └── sprint_05_integration_and_release.md
├── 04_guides/                    # Hướng dẫn quy trình & Runbooks (How-To)
│   ├── development_setup.md      # Thiết lập môi trường phát triển
│   └── verification_and_qa_loop.md # Quy trình kiểm định 6 Pha tự động
└── 05_security/                  # Tiêu chuẩn an ninh AgentShield (Policy)
    └── security_and_compliance.md # Bảo mật OS Vault & Bộ lọc Redaction
```

---

## 🧭 Hướng Dẫn Điều Hướng Nhanh Theo Vai Trò (Navigation Guide)

- **Dành cho Lập Trình Viên Backend / CSDL**:
  1. Đọc [docs/01_architecture/system_overview.md](file:///d:/TictokUpload411/docs/01_architecture/system_overview.md) để nắm cấu trúc phân tầng.
  2. Tra cứu [docs/02_specifications/database_schema.md](file:///d:/TictokUpload411/docs/02_specifications/database_schema.md) để xem chi tiết 24 bảng CSDL và ràng buộc khóa ngoại.
  3. Bắt đầu thực thi các tasks trong [docs/03_work_breakdown/sprint_01_core_infrastructure.md](file:///d:/TictokUpload411/docs/03_work_breakdown/sprint_01_core_infrastructure.md).

- **Dành cho Kỹ Sư UI / Frontend PyQt6**:
  1. Đọc [docs/02_specifications/ui_ux_specification.md](file:///d:/TictokUpload411/docs/02_specifications/ui_ux_specification.md) để nắm bố cục bảng kép và delegates.
  2. Xem kỹ [docs/02_specifications/api_and_signal_contracts.md](file:///d:/TictokUpload411/docs/02_specifications/api_and_signal_contracts.md) để kết nối Slots với Signal Bus.
  3. Triển khai các tasks trong [docs/03_work_breakdown/sprint_04_fluent_ui_presentation.md](file:///d:/TictokUpload411/docs/03_work_breakdown/sprint_04_fluent_ui_presentation.md).

- **Dành cho Kỹ Sư Tích Hợp SDK & Đa Luồng**:
  1. Đọc [docs/02_specifications/sdk_integration_protocol.md](file:///d:/TictokUpload411/docs/02_specifications/sdk_integration_protocol.md) về SamMonny SDK official direct post.
  2. Nắm vững mô hình worker thread tại [docs/01_architecture/adr/0004-async-worker-thread-model.md](file:///d:/TictokUpload411/docs/01_architecture/adr/0004-async-worker-thread-model.md).
  3. Thực thi [docs/03_work_breakdown/sprint_03_concurrency_workers.md](file:///d:/TictokUpload411/docs/03_work_breakdown/sprint_03_concurrency_workers.md).

- **Dành cho Quản Trị Dự Án & QA / Security**:
  1. Theo dõi lộ trình và tiến độ tại [docs/03_work_breakdown/wbs_and_roadmap.md](file:///d:/TictokUpload411/docs/03_work_breakdown/wbs_and_roadmap.md).
  2. Thực thi kiểm định chất lượng theo [docs/04_guides/verification_and_qa_loop.md](file:///d:/TictokUpload411/docs/04_guides/verification_and_qa_loop.md).
  3. Giám sát an ninh thông tin theo [docs/05_security/security_and_compliance.md](file:///d:/TictokUpload411/docs/05_security/security_and_compliance.md).

