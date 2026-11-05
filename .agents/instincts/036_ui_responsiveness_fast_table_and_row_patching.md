# Instinct 036: UI Responsiveness — Fast Fluent Table, Row Patching, Signal Throttling

Kế hoạch gốc: `docs/03_work_breakdown/ui_responsiveness_fix_plan.md` (Sprint P0 = T1–T4).
Benchmark tái lập: `scratch/perf/bench_p0.py` (offscreen, 500 dòng × 29 cột).

## 1. Fluent `TableWidget` là nguồn giật chính — luôn dùng `FastTableWidget`
- `qfluentwidgets` (1.11.x) gọi `viewport().update()` TOÀN BỘ bảng ở mỗi lần đổi hover row, pressed row, selection và vẽ mọi ô bằng delegate Python ⇒ ~85 ms mỗi lần rê chuột, ~170 ms mỗi cú click.
- `src/presentation/widgets/fast_table.py::FastTableWidget` giữ nguyên giao diện Fluent nhưng chỉ repaint các dòng đổi trạng thái (8 ms / 12 ms). **Mọi bảng mới phải kế thừa `FastTableWidget`, không dùng `qfluentwidgets.TableWidget` trực tiếp.**
- Nền dòng của ô giữa phải `fillRect(option.rect)` đúng khung ô; nới rộng 1px sẽ chồng alpha tạo vạch dọc ở ranh giới ô.
- `FastTableWidget` dùng hàm riêng tư `_setHoverRow/_setPressedRow/updateSelectedRows` của Fluent ⇒ khi nâng cấp `PyQt6-Fluent-Widgets` phải chạy `tests/unit/test_ui_responsiveness_p0.py`.
- Tô highlight lấy dòng từ `selectionModel().selection()` (O(ranges)). **Nhưng hành động nghiệp vụ (xóa, gán proxy…) vẫn lấy dòng từ `selectedIndexes()`**: range selection có thể bao cả dòng đang bị ẩn bởi bộ lọc tìm kiếm.

## 2. Không bao giờ quét tuyến tính tìm dòng theo id
- Dùng `RowIndex` (map id → item cột 0; `item.row()` do Qt cập nhật nên đúng cả sau khi sort): `profile_table.row_for_profile_id()`, `video_table.find_row_by_video_id()`.

## 3. `profile_updated` → vá dòng, không reload bảng
- `main_window._on_profile_updated` chỉ xếp hàng patch; `_flush_profile_patches` (QTimer single-shot 250 ms) gộp và gọi `profile_table.update_profile_row()` (~1 ms/dòng thay vì ~270 ms reload + DB + quét psutil).
- Fallback 1 lần `refresh_profiles()` khi profile chưa hiển thị, bị trash hoặc chuyển project.
- Lưu ý (lỗi có sẵn, chưa sửa): bảng đọc `t_follows/t_views/t_video/earned/qg/kyc` trong khi DB/emitter dùng `total_followers/total_views/total_videos/money_earned/country/state_kyc` ⇒ các cột đó luôn hiển thị 0.

## 4. Không ghi SQLite trong slot GUI
- `writer_lock` dùng chung theo DB: slot GUI ghi DB khi worker upload đang giữ giao dịch sẽ block tới `busy_timeout` (đo được ~1 s). Ghi ở worker (`ProfileRuntimeSyncWorker._persist_deltas`, gom theo status bằng `bulk_update_fields`), slot chỉ cập nhật ô.

## 5. Giới hạn tần suất tín hiệu tiến độ từ worker
- `UploadWorker._on_progress` phát progress/stage tối đa 4 Hz/video (`PROGRESS_MIN_INTERVAL_S`), luôn phát mốc 100%. Đồng hồ inject qua `clock=` để test xác định.

## 6. Kiểm thử widget Fluent
- Không để GC xóa một Fluent `TableWidget` top-level đang hiển thị (PyQt access violation — lỗi sẵn có của thư viện). Trong test: `close()` + `deleteLater()` + `processEvents()`; event filter phải có parent là widget được lọc.
