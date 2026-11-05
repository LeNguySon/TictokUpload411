# Instinct 050: Bản quyền offline (Ed25519) & khóa tính năng theo gói

## Kiến trúc (2026-11-05)
- Domain `src/domain/licensing/`: `Plan`/`Feature` (gói cộng dồn), `LicenseClaims`, `entitlements`
  (`has`/`require`, tự kiểm tra hạn ở mỗi lần gọi).
- Infra `src/infrastructure/licensing/`: `verifier.py` (định dạng `TAVM1.<payload>.<sig>`), `trusted_keys.py`
  (public key + danh sách thu hồi), `machine_id.py` (hash MachineGuid + serial ổ hệ thống), `license_store.py` (DPAPI).
- `LicenseService`: chữ ký → đúng máy → chống lùi đồng hồ (dung sai 24h) → hạn. Chỉ lưu key khi hợp lệ.
- `main.py` chặn khởi động; `main_window._check_license` khóa app khi hết hạn lúc đang chạy.
- Công cụ cấp key: `tools/license_issuer/issuer.py` — **không** được import từ `src/`, không đóng gói.

## Khi thêm tính năng mới
- Quyết định nó thuộc gói nào ⇒ chặn **cả 2 lớp**: handler UI (`self._feature_allowed(Feature.X)`, nút disable
  trong `_apply_license`) **và** tầng service/worker (`entitlements.require/has`). Chỉ chặn UI là chưa đủ.
- Dialog mới làm tăng số dialog trong `test_all_dialogs_use_fluent_headers_and_margins` (hiện 20).

## Test
- `tests/conftest.py::test_license` (autouse): mọi test chạy với Gói 3 giả + `TAVM_LICENSE_FILE` tạm ⇒ không đụng
  `%APPDATA%\TAVM\license.dat` thật. Test về gói tự gọi `entitlements.set_current(...)`.
- Không bao giờ in key / khóa bí mật ra log hoặc chat; repo không được chứa `PRIVATE KEY`.
