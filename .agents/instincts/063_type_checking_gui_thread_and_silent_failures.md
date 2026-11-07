# Instinct 063: mypy thật sự chạy, DB rời GUI thread, lỗi không còn bị nuốt (2026-11-07)

## Môi trường
- PyQt6 6.12.0 có stub `.pyi` sai cú pháp (`QtGui.pyi`, `QtDBus.pyi`: `*args: X, /`), nên mypy dừng ở site-packages
  và KHÔNG kiểm tra dòng code nào của dự án. `follow_imports=skip` không cứu được vì mypy vẫn phải parse stub.
  ⇒ Ghim `PyQt6>=6.8.0,<6.12` (6.11.0 đã kiểm: mọi stub đều parse được). Muốn nâng PyQt6 thì chạy
  `python -c "import ast,glob;[ast.parse(open(f,encoding='utf-8').read()) for f in glob.glob('.venv/Lib/site-packages/PyQt6/*.pyi')]"` trước.
- Không thay gói Qt (`pip install`) khi đang có pytest chạy: `qtcore.pyd` bị khóa ⇒ cài dở, PyQt6/PyQt6-Qt6 lệch
  phiên bản ⇒ `DLL load failed`.
- `sammonny` phải cài từ `vendor/*.whl` (`pip install --no-index --find-links vendor sammonny==1.8.3`), không cài
  editable từ repo SDK ngoài (metadata pip báo sai phiên bản, máy khác không tái lập được).
- CI: `.github/workflows/ci.yml` (windows-latest, `QT_QPA_PLATFORM=offscreen`) chạy pha 1–4. Ở chế độ offscreen,
  test font-metrics trong `test_dialog_design_standards.py` bị skip (chạy native mới chạy test này).

## Quy ước typing với stub Qt
- Accessor Qt trả `X | None` (horizontalHeader, selectionModel, mimeData, model, item, QThreadPool.globalInstance).
  Header thì dùng `h_header()`/`v_header()` trong `widgets/table_helpers.py`; chỗ khác thì guard `is None`.
- Override event handler/paint phải nhận `QXxxEvent | None` / `QPainter | None` (Liskov), rồi guard.
- Worker con khai báo `self.signals: SubSignals = SubSignals()` để mypy thấy signal riêng.
  `ThreadPoolManager.dispatch/track_worker` nhận mọi `QRunnable`.

## GUI thread
- Mẫu chuẩn: tách hàm đọc DB thuần (`fetch_health_data`, `load_radar_inputs`, `list_trashed_profiles`...) rồi gọi
  `run_task(fn, ..., on_result, on_error)`. Callback chạy trên GUI thread qua queued signal.
- KHÔNG dùng `ThreadPoolExecutor` + `QTimer(self)` poll: callback chạm vào dialog đã bị huỷ ⇒ access violation
  (đó chính là lỗi crash chập chờn ghi ở instinct 059). Callback phải qua guard
  `not self._closed and not sip.isdeleted(self)`; set `_closed` trong `done()` và `closeEvent()`.
- Test dialog tải dữ liệu bất đồng bộ phải `assert drain_ui_tasks()` trước khi assert nội dung bảng.
- Xóa vĩnh viễn (dọn thùng rác) phải hỏi xác nhận (`confirm_permanent_delete`).
- Còn lại (chưa xử lý): `main_window.py` và nhiều dialog vẫn gọi repository đồng bộ trên GUI thread
  (vd. `_on_edit_profile` → `profile_repo.get_by_id`, `ProxyManagerDialog.refresh_proxies`).

## Lỗi bị nuốt
- `except Exception: pass` từng che 3 lỗi thật: `vault.save_credentials` (method không tồn tại), cookie nạp lỗi
  vẫn được đếm là đã nạp, "Xoay IP" lỗi vẫn báo thành công. Nay các handler chung đều `logger.debug(...)`; lỗi
  người dùng cần biết thì phải hiện InfoBar. `except RuntimeError: pass` khi emit lên object đã huỷ là cố ý, giữ nguyên.
- `except ... as exc` bên trong một `except ... as exc` khác sẽ XÓA biến ngoài khi thoát handler: đặt tên khác.

## Nợ bảo mật đã biết (AgentShield)
- Bảng `profiles` vẫn lưu plaintext `password`, `email_backup_password`, `cookies_json`/`cookie` (có test khẳng định
  `imported["password"] == ...`). Chỉ `refresh_token` được chuyển sang Vault (token_manager). Muốn chuyển các cột
  này sang Vault/DPAPI thì cần migration riêng.

## SamMonny SDK main sau 1.8.3 (commit 64c53a0, eacbb93, 2026-11-07): độ tương thích
- Vẫn ghi `version = 1.8.3` dù code đã khác bản phát hành ⇒ KHÔNG đóng gói vào `vendor/` khi chưa tăng phiên bản.
- Lỗi SDK: `platforms/tiktok.py` dùng `random.uniform` khi bấm nút Post của Studio (HumanMouse) nhưng không
  `import random` ⇒ NameError bị nuốt, nhánh `btn.click()` bị bỏ qua, upload Studio kết thúc ambiguous.
  App vá bằng `_install_sdk_compat_shims()` trong `sammonny_adapter.py` (test: `test_sdk_contract.py`).
- Hybrid: thử VOD AWS4 thật nhưng lỗi thì vẫn rơi về phiên TOS giả lập (`tos_sess_` ⇒ sleep thay vì PUT);
  URL upload/`store_uri`/`upload_id` có giá trị dự phòng tự bịa; lỗi CommitUploadInner chỉ warning.
  ⇒ Giữ `COOKIE_HYBRID_AVAILABLE = False`; test chặn bật lại khi SDK còn đường giả lập.
- Kiểm tra app với SDK chưa phát hành mà không đổi venv: `PYTHONPATH=<sdk>/sdk/python python -m pytest tests`.
