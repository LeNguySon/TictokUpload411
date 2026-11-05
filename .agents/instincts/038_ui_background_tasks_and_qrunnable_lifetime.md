# Instinct 038: UI Background Tasks (P1) and QRunnable/Signal Lifetime

Kế hoạch: `docs/03_work_breakdown/ui_responsiveness_fix_plan.md` (Sprint P1 = T5–T7). Tiếp nối instinct 036.

## 1. Mọi I/O phát sinh từ thao tác UI → `run_task` / `TaskWorker`
- `src/application/workers/task_worker.py`: `run_task(fn, *args, on_result=, on_error=)` chạy trên `ui_thread_pool()` (4 luồng, **tách khỏi `QThreadPool.globalInstance()`** nơi upload chạy hàng phút) và gọi callback trên GUI thread.
- Trong `TikTokManagerMainWindow` dùng `self._run_bg(...)`: bọc callback để bỏ qua `RuntimeError` khi cửa sổ đã bị hủy.
- Hàm chạy nền **chỉ nhận giá trị/đối tượng thuần** (repo, service, list id) được bắt trước khi dispatch; không đọc widget trong luồng nền. Đọc widget (selection, switch, spinbox) trên GUI rồi truyền vào closure.
- `TaskWorker` cố ý **không** gọi `MemoryManager.trim_working_set()` như `BaseWorker`: trim sau mỗi task nhỏ đẩy RAM của app ra pagefile ngay trước khi GUI cần.

## 2. Nạp bảng bất đồng bộ (T5)
- `refresh_profiles()` / `refresh_videos()` đọc SQLite trên UI pool; `_apply_profile_load(gen, rows)` / `_apply_video_load` bỏ qua kết quả cũ bằng generation token.
- Lần nạp đầu (`_load_initial_data`) vẫn đồng bộ để cửa sổ không mở ra trống.
- **Test**: sau thao tác gây refresh/close/rotate/clean/drop phải gọi `drain_ui_tasks()` (bên trong khối `with patch(...)` nếu task cần mock) trước khi assert. Dialog quét thư mục có debounce 300 ms ⇒ dùng `qtbot.waitUntil`.

## 3. Thanh tiến độ bằng delegate (T6)
- Cột 10 bảng video: `ProgressBarDelegate` vẽ từ `Qt.ItemDataRole.UserRole` (int 0–100). Không tạo `setCellWidget` cho từng dòng (500 widget ≈ 300 ms). API: `video_table.progress_value(video_id)`.

## 4. Vòng đời QRunnable / signals — nguyên nhân access violation ngẫu nhiên
- **Không gắn signals của worker làm con của widget** (`ProfileRuntimeSyncWorker(parent=self)` cũ): khi widget bị hủy, Qt xóa signals trên GUI thread trong khi luồng worker có thể đang emit ⇒ use-after-free.
- Worker `setAutoDelete(False)` do Python sở hữu: phải có tham chiếu mạnh **ổn định** tới khi `finished` được xử lý. `ThreadPoolManager` giữ trong `_INFLIGHT` (cấp module, không phụ thuộc singleton bị `reset_instance()`); closure `_cleanup` không được tham chiếu tới manager (tránh chu trình để GC dọn giữa lúc worker còn chạy). `task_worker._running` làm điều tương tự cho `TaskWorker`.
- `QThreadPool` cấp module phải có parent là `QCoreApplication` (và kiểm tra `sip.isdeleted`): pool không parent bị Python finalizer hủy sau `QApplication` ⇒ crash khi thoát.
- Đo: bộ 3–4 file test chạy lặp 15 lần: 0 crash (trước: HEAD 1/5, P1 chưa sửa 2/3).

## 5. Kiểm thử khi có agent khác cùng sửa repo
- Kiểm chứng thay đổi của mình trên snapshot sạch: `git archive HEAD | tar -x -C scratch/<snap>` rồi chép riêng các file của mình vào. Test dùng DB mặc định `data/app.db` sẽ fail trong snapshot (thư mục `data/` bị gitignore) — đó là lỗi môi trường, không phải code.
