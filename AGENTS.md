# AGENTS.md — Quy Chuẩn Quản Trị AI Agent Dự Án TikTok Manager (TAVM-2026-WIN)
## Tiêu Chuẩn Kỹ Thuật: ECC Development Lifecycle (affaan-m/ecc)

Tài liệu này là quy chế bắt buộc cho toàn bộ AI Coding Agents (Antigravity, Claude, Codex, Gemini) khi hoạt động trong codebase `d:\TictokUpload411`. Mọi tác vụ đều phải tuân thủ nghiêm ngặt kỹ năng:
**`ecc-development-workflow`** (đặt tại [.agents/skills/ecc-development-workflow/SKILL.md](file:///d:/TictokUpload411/.agents/skills/ecc-development-workflow/SKILL.md)).

---

## 1. Nguyên Tắc Cốt Lõi Của ECC (Core Principles)

1. **Chu Trình Khép Kín 7 Pha**:
   $$\text{Plan} \longrightarrow \text{Test (TDD)} \longrightarrow \text{Implement} \longrightarrow \text{Review} \longrightarrow \text{Verify} \longrightarrow \text{Remember} \longrightarrow \text{Improve}$$
2. **Quy Mô Dự Án (Right-Sizing Tier)**: 
   - Dự án được xếp hạng **Tier 4 — Large** (Kiến trúc phân tầng Clean Architecture, 24 bảng CSDL SQLite, tích hợp SamMonny Tri-Modal SDK, giao diện đa luồng PyQt6).
   - **Bắt buộc vượt qua 2 chốt chặn kiểm duyệt**:
     - **GATE 1 (Plan Approval)**: Phải lập kế hoạch, phân tích DAG và được người dùng phê duyệt trước khi can thiệp mã nguồn.
     - **GATE 2 (Delivery Verification)**: Phải chạy đủ 6 pha kiểm định (Verification Loop) và được người dùng xác nhận trước khi bàn giao.
3. **Phát Triển Hướng Kiểm Thử (Strict TDD - Test Driven Development)**:
   - **RED**: Viết unit test / integration test mô tả hành vi mong đợi trước, chạy test để xác nhận test thất bại vì thiếu code.
   - **GREEN**: Viết mã nguồn tối thiểu (Surgical implementation) vừa đủ để test chuyển sang màu xanh (Pass).
   - **REFACTOR**: Tối ưu hóa, dọn dẹp mã nguồn nhưng giữ test luôn pass 100%.
4. **Phòng Thủ Nhiều Lớp AgentShield**:
   - Không bao giờ lưu trữ hoặc in Access Token, Cookie, Private Key dạng plaintext.
   - Dữ liệu nhạy cảm được bảo vệ bởi Windows DPAPI và Windows Credential Manager.
5. **Hiệu Năng & Ổn Định Desktop**:
   - Tuyệt đối không block GUI Main Thread (mọi I/O, SDK upload, query CSDL chạy trên `QThreadPool`).
   - SQLite luôn chạy với `PRAGMA journal_mode = WAL;`, `foreign_keys = ON;`, `busy_timeout = 10000;`.
   - Giải phóng RAM Chromium thông qua `MemoryManager.trim_working_set()` sau mỗi tác vụ.

---

## 2. Quy Trình Kiểm Định 6 Pha (6-Phase Verification Loop)

Trước khi kích hoạt GATE 2 hoặc thông báo hoàn thành tác vụ, Agent phải kiểm tra tuần tự:
1. **Phase 1: Build & Import**: Toàn bộ module import thành công không có lỗi Circular Dependency.
2. **Phase 2: Type Checking**: Kiểm tra kiểu tĩnh với `mypy` hoặc `pyright` (Zero type errors).
3. **Phase 3: Lint & Formatting**: Kiểm tra chuẩn code PEP 8 với `ruff check .`
4. **Phase 4: Test Suite Execution**: Toàn bộ unit tests và integration tests vượt qua với `pytest`.
5. **Phase 5: AgentShield Security Audit**: Không rò rỉ token, secret hoặc đường dẫn cứng nhạy cảm.
6. **Phase 6: Git Diff & Hygiene**: Rà soát `git diff`, đảm bảo không có file rác, file tạm `.pyc` hay debug print.

---

## 3. Hệ Thống Ghi Nhớ Bản Năng (Instinct Memory)

Mọi bài học kinh nghiệm, cách khắc phục lỗi hoặc thói quen kỹ thuật của dự án phải được ghi nhận vào thư mục:
`d:\TictokUpload411\.agents\instincts/`
để các agent sau không lặp lại sai lầm của agent trước.

