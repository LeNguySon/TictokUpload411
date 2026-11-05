# Kế hoạch: Cấp key bản quyền thật cho người dùng (GATE 1 — chờ duyệt)

Ngày lập: 2026-11-05 · Trạng thái: **Bản nháp, chưa triển khai code**

## 1. Hiện trạng (khảo sát)
- Repo **không có** mã bản quyền nào: không có module license/activation, không kiểm tra hạn, không ràng buộc máy.
- Footer `main_window.py:374` là chuỗi cứng: `Xin chào user | Thời gian hết hạn: 07-08-2026 | Gói: Goepro | Version: 1.5.5.2`.
  Version `1.5.5.2` lệch với `pyproject.toml` (`2.0.0`).
- PROJECT_SPEC §8 nhắc `licensing.py` (runtime DDL) của dự án kế thừa Gloglin2609 — chưa được port.
- Phụ thuộc đã có sẵn: `cryptography` (Ed25519), `keyring` + `pywin32` (Credential Manager / DPAPI). Không cần thêm thư viện.

## 2. Mục tiêu
1. Nhà phát triển phát hành key cho từng khách hàng (tên, gói, hạn, giới hạn tính năng, máy).
2. App kiểm tra key **offline** bằng chữ ký số — không thể tự sinh key giả nếu không có khóa bí mật.
3. Footer, giới hạn tính năng và cảnh báo hết hạn lấy từ key thật; version lấy từ metadata gói.
4. Không lưu khóa bí mật trong app/repo; key của khách lưu mã hóa (DPAPI / Credential Manager).

## 3. Thiết kế

### 3.1 Định dạng key
`TAVM1.<base64url(payload_json)>.<base64url(chữ_ký_Ed25519)>`

Payload (claims):
| Trường | Ý nghĩa |
|---|---|
| `lid` | Mã license (UUID), dùng để thu hồi |
| `sub` | Tên hiển thị khách hàng ("Xin chào …") |
| `plan` | `trial` / `basic` / `pro` (tên gói hiển thị) |
| `limits` | ví dụ `{"max_profiles": 50, "max_parallel_uploads": 3}` |
| `iat`, `exp` | Ngày cấp, ngày hết hạn (UTC) |
| `mid` | Hash máy được phép (tùy chọn; `null` = key chưa gắn máy) |
| `min_ver`/`max_ver` | Dải version được dùng (tùy chọn) |

- App nhúng **public key**; private key chỉ nằm trên máy nhà phát triển (công cụ phát hành, ngoài repo app).
- Hỗ trợ xoay khóa: header chứa `kid`, app giữ danh sách public key hợp lệ.

### 3.2 Mã máy (machine id)
- `SHA-256(MachineGuid registry + serial ổ hệ thống + salt app)` → rút gọn hiển thị dạng `XXXX-XXXX-XXXX-XXXX`.
- Chỉ gửi/hiển thị **hash**, không gửi dữ liệu phần cứng thô.
- Đổi phần cứng nhỏ có thể làm đổi mã ⇒ cần quy trình "chuyển máy" (mục 3.4).

### 3.3 Lưu trữ & kiểm tra phía app
- Key lưu trong Windows Credential Manager (`keyring`) hoặc file `%APPDATA%\TAVM\license.bin` mã hóa DPAPI.
- Kiểm tra khi khởi động và mỗi 6 giờ (chạy trên `QThreadPool`, không block GUI):
  chữ ký → `mid` khớp → chưa hết hạn → không nằm trong danh sách thu hồi đã cache.
- Chống quay lùi đồng hồ: lưu "thời điểm lớn nhất từng thấy" (mã hóa); nếu giờ máy lùi > 24h ⇒ coi như cảnh báo/khóa.
- Hết hạn: cảnh báo InfoBar ở 14/7/1 ngày; sau hạn ⇒ hành vi theo quyết định D2 bên dưới.

### 3.4 Kích hoạt (2 chế độ — chọn ở D1)
- **A. Offline thuần**: khách gửi mã máy → nhà phát triển chạy công cụ phát hành → gửi key đã gắn `mid`. Đơn giản,
  không cần server; thu hồi chỉ có hiệu lực khi phát hành bản cập nhật chứa danh sách thu hồi.
- **B. Server kích hoạt nhỏ** (FastAPI + SQLite/Postgres, HTTPS): khách nhập key gốc → server kiểm tra số máy đã kích hoạt
  → trả về key đã gắn `mid` có hạn ngắn (vd 30 ngày, tự gia hạn khi online). Có thu hồi, đếm số máy, chuyển máy tự phục vụ.
  Offline tối đa 7 ngày (grace period) trước khi yêu cầu kết nối lại.

### 3.5 Giao diện
- `LicenseActivationDialog` (Fluent, đúng chuẩn các dialog đã căn chỉnh): hiển thị mã máy + nút sao chép, ô dán key,
  thông báo lỗi rõ ràng (sai chữ ký / sai máy / hết hạn).
- Hiện khi chưa có key hợp lệ; truy cập lại từ menu "Bản quyền".
- Footer: `Xin chào {sub} | Hết hạn: {exp:dd-MM-yyyy} | Gói: {plan} | Version: {importlib.metadata.version}`.

### 3.6 Giới hạn tính năng theo gói
- `LicensePolicy` ở domain; kiểm tra tại service (không chỉ ở UI): số hồ sơ tối đa trong `ProfileService.create`,
  số luồng upload song song trong dispatcher upload.

### 3.7 Công cụ phát hành (cho nhà phát triển)
- `tools/license_issuer/` (CLI, **không đóng gói kèm app**): `keygen`, `issue --sub --plan --days --mid`, `revoke`,
  sổ ghi các key đã phát hành (CSV/SQLite). Private key bảo vệ bằng mật khẩu (PKCS#8 encrypted).

### 3.8 Giới hạn cần nói rõ
Chữ ký số ngăn **làm giả key**, nhưng app Python phía client vẫn có thể bị sửa để bỏ qua kiểm tra. Giảm thiểu: build
bằng Nuitka/PyInstaller, kiểm tra ở nhiều điểm trong service; giá trị bảo vệ thật nằm ở chế độ B (server). Không hứa
"không thể crack".

## 4. Cấu trúc mã dự kiến (Clean Architecture)
```
src/domain/licensing/         claims.py (LicenseClaims, Plan), policy.py (LicensePolicy, giới hạn)
src/infrastructure/licensing/ verifier.py (Ed25519), machine_id.py, store.py (DPAPI/keyring), clock_guard.py
src/application/services/     license_service.py (trạng thái, tín hiệu thay đổi, kiểm tra định kỳ)
src/presentation/dialogs/     license_activation_dialog.py
tools/license_issuer/         cli.py (ngoài gói phát hành)
```

## 5. Lộ trình (TDD từng pha — RED → GREEN → REFACTOR)
| Pha | Nội dung | Test chính |
|---|---|---|
| L1 | Định dạng key, verifier, công cụ phát hành (keygen/issue) | key hợp lệ pass; sửa 1 byte payload ⇒ fail; sai `kid`; hết hạn |
| L2 | Machine id, lưu trữ DPAPI/keyring, clock guard | sai máy ⇒ fail; lưu/đọc lại; đồng hồ lùi ⇒ cảnh báo; test không chạm Credential Manager thật |
| L3 | Dialog kích hoạt + footer thật + version từ metadata | dialog dán key; footer hiển thị đúng claims; không còn chuỗi cứng |
| L4 | Giới hạn theo gói ở service + hành vi hết hạn | vượt `max_profiles` bị chặn; cảnh báo 14/7/1 ngày |
| L5 (tùy D1) | Server kích hoạt, gia hạn online, thu hồi, grace 7 ngày | API contract test với server giả; offline quá grace ⇒ khóa |

Ước lượng: L1–L4 ≈ 2–3 phiên làm việc; L5 là dự án riêng (server + triển khai hosting).

## 6. Quyết định cần người dùng chốt
- **D1**: Offline thuần (A) hay có server kích hoạt (B)? Đề xuất: làm A trước (L1–L4), thiết kế sẵn để nâng lên B.
- **D2**: Hết hạn thì: (a) chỉ xem dữ liệu, chặn mở trình duyệt/upload — đề xuất; hay (b) khóa toàn bộ app?
- **D3**: Danh sách gói và giới hạn (tên gói, số hồ sơ, số upload song song, có bản dùng thử bao nhiêu ngày?).
- **D4**: Một key được dùng trên bao nhiêu máy, cho chuyển máy mấy lần?
