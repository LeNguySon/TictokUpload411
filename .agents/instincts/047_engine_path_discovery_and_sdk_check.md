# Instinct 047: Engine/Daemon Path Discovery & SDK Compatibility Check

## Kiểm tra cập nhật SDK / Orbita (2026-11-05)
- SamMonny SDK mới nhất = 1.8.1 (pyproject của repo SDK) = bản đang cài editable = wheel `vendor/` (so hash 92/92 file).
  Không có bản mới hơn để nâng cấp.
- Đối chiếu API: `scratch/perf/sdk_audit.py` (AST: method + kwargs trên GoLogin, SamMonnyDaemonClient, AntidetectEngine,
  TikTokPublisherAdapter, TikTokDirectPostClient, MemoryManager) + kiểm tra mọi symbol import ⇒ 0 sai khác.
  Chạy lại 2 bước này mỗi khi SDK đổi version; test hợp đồng: `tests/unit/test_sdk_contract.py`.
- Orbita mới nhất trên máy: `orbita-152` (đã được dùng).

## Không hard-code đường dẫn theo máy
- `src/infrastructure/browser/engine_paths.py`: `discover_orbita_executable()` (env `TAVM_ORBITA_PATH`, rồi quét
  `orbita-<N>`/`orbita-browser-<N>` dưới các engine root — **N lớn nhất thắng** — rồi Chrome/Edge hệ thống),
  `daemon_profiles_dir()`, `daemon_binary_candidates()`, `sammonny_roots()`.
- `OrbitaLauncher.DAEMON_PROFILES_DIR` vẫn là thuộc tính lớp (test monkeypatch được) nhưng lấy từ discovery.
- Vị trí cũ chỉ còn là fallback cuối trong `engine_paths.py`. Danh sách biến môi trường: `docs/04_guides/development_setup.md` mục 2b.
- Test: `tests/unit/test_engine_paths.py` (có kiểm tra không còn `C:\Users\sonson` trong launcher/daemon manager).
