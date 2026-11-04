# Hàng Rào Bảo Vệ An Ninh & Cơ Chế Hooks (ECC AgentShield & Guardrails)

Tài liệu này định nghĩa hệ thống **AgentShield** và cơ chế **Hàng Rào Bảo Vệ (Guardrails)** theo chuẩn ECC ([affaan-m/ecc](https://github.com/affaan-m/ecc)), nhằm bảo đảm đặc vụ AI hoạt động hoàn toàn an toàn, không bao giờ gây tổn hại đến hệ thống, không làm thất thoát dữ liệu và không tự ý thực thi các lệnh nguy hiểm.

---

## 🛡️ 1. Triết Lý Bảo Mật 3 Lớp Của AgentShield

```
+-----------------------------------------------------------------------------------+
|                        HỆ THỐNG PHÒNG THỦ AGENTSHIELD                             |
+-----------------------------------------------------------------------------------+
|  [LỚP 1] PRE-EXECUTION FILTER   : Chặn lệnh nguy hại trước khi gọi Tool          |
|  [LỚP 2] RUNTIME ISOLATION       : Thực thi phẫu thuật, không sửa ngoài phạm vi  |
|  [LỚP 3] POST-EXECUTION AUDIT   : Quét mã nguồn, phát hiện rò rỉ trước khi commit|
+-----------------------------------------------------------------------------------+
```

---

## 🚫 2. Danh Mục Lệnh & Hành Vi Bị Cấm Tuyệt Đối (Zero-Tolerance Blacklist)

Bất kỳ hành vi nào dưới đây đều bị kích hoạt cơ chế tự động hủy bỏ (*Immediate Work-Stop*):

1. **Thao tác File Hủy diệt (Destructive File Operations)**:
   - Cấm chạy các lệnh xóa đệ quy thiếu kiểm soát: `rm -rf /`, `rm -rf ~`, `Remove-Item -Recurse C:\`.
   - Cấm ghi đè hoặc xóa các file lịch sử VCS: `.git/`, `.git/config`, `git reset --hard` khi chưa được người dùng phê chuẩn.
2. **Tiết lộ hoặc Thu thập Bí mật (Secrets Handling)**:
   - Tuyệt đối không đọc, in ra terminal, hoặc truyền tải nội dung các file chứa khóa bí mật: `id_rsa`, `.env.production`, `credentials.json`, `keystore`.
   - Cấm ghi log chứa chuỗi mật khẩu, token JWT, hoặc API Key.
3. **Thực thi Mã Từ xa Không Tin cậy (Remote Code Execution)**:
   - Cấm chạy các lệnh tải và thực thi trực tiếp: `curl ... | bash`, `wget ... | sh`, `powershell -Command "iex (iwr ...)"`.
4. **Bypass Kiểm soát & Vượt ranh giới (Privilege Escalation / Sandbox Escape)**:
   - Cấm tự ý sửa đổi quyền bảo mật hệ thống, can thiệp registry, tắt tường lửa hoặc bypass cơ chế kiểm tra quyền hạn.

---

## ⚡ 3. Cơ Chế Hooks Tự Động Hóa (Lifecycle Hook Triggers)

Hệ thống điều phối các điểm can thiệp tự động (*Hooks*) trong suốt phiên làm việc của AI:

| Điểm Kích Hoạt (Hook Point) | Thời Điểm Chạy | Trách Nhiệm Kỹ Thuật |
| :--- | :--- | :--- |
| **`PreToolUse`** | Trước khi chạy shell hoặc tool ghi file | - Kiểm tra lệnh nằm trong whitelist an toàn.<br>- Nhắc nhở sử dụng session persistence (tmux / background task) cho lệnh chạy dài.<br>- Ngăn chặn việc ghi đè file cấu hình nhạy cảm. |
| **`PostToolUse`** | Ngay sau khi tool thực thi xong | - Tự động format code (Prettier / Ruff) nếu có sửa file.<br>- Báo cáo nếu câu lệnh trả về exit code khác 0. |
| **`PreCompact`** | Trước khi tóm tắt ngữ cảnh (Context Compaction) | - Bảo toàn các mục tiêu kiến trúc và Task DAG hiện tại.<br>- Trích xuất nhanh các bài học (Instincts) trước khi context bị thu gọn. |
| **`Stop`** | Khi đặc vụ chuẩn bị kết thúc lượt trả lời | - Đảm bảo không để lại tiến trình nền mồ côi (*zombie processes*).<br>- Nhắc nhở người dùng về trạng thái của các Chốt Chặn (Gate 1 / Gate 2). |

---

## 🔍 4. Danh Mục Quét Bí Mật Tự Động Trước Khi Commit (Pre-Commit Security Scan)

Trước khi kích hoạt **GATE 2 (Commit Gate)**, bắt buộc chạy quét mã nguồn với các biểu thức chính quy (Regex Pattern) sau để phát hiện rò rỉ:

```bash
# Quét tìm API Key và Secret Token phổ biến
git diff --cached | grep -E -i \
  "(api[_-]?key|secret|token|password|bearer|aws_access_key_id|private[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9/\+=_\-]{8,}['\"]"
```

- Nếu phát hiện bất kỳ chuỗi nhạy cảm nào: **Dừng ngay lập tức**, thông báo cho người dùng và chuyển khóa bí mật sang biến môi trường (`.env`).
