# Instinct 012: TikTok Studio Native Cloud Scheduling & Project-Specific Video Folders

## Context & Problem
Creators running multiple TikTok campaigns (e.g., Japan, Korea, US) required two critical operational capabilities:
1. **TikTok Studio Native Cloud Scheduling**: Rather than relying purely on the local computer being powered on at publication time, users need the ability to upload drafts directly into TikTok Creator Studio and toggle the native "Schedule video" option (15 min - 10 days window, 5-minute increments), allowing videos to publish from TikTok's cloud even if the PC is shut down.
2. **Project-Specific Video Folders**: When managing distinct geographical or niche groups (e.g., Japan vs. Korea), users need each project to be bound to a dedicated local directory so that file pickers and batch uploaders automatically open the corresponding folder.

## Engineering Solution
1. **Database Schema & Pre-Migration**:
   - Added `video_folder TEXT DEFAULT NULL` to `projects` table.
   - Enhanced `runner.py` with pre-migration verification using PRAGMA checks to safely add `video_folder` to existing production databases.
2. **Project Video Folder Management**:
   - `ProjectRepository.create` and `ProjectRepository.update`: Support storing and updating `video_folder`.
   - `ProjectManagerDialog`: Added input field and folder browse button (`QFileDialog.getExistingDirectory`) for `video_folder`. Extended table to 7 columns with column "Thư Mục Video".
   - `TikTokManagerMainWindow._get_initial_video_pick_folder`: Automatically queries the active project's `video_folder` and directs `QFileDialog.getOpenFileNames` to that location.
3. **TikTok Studio Native Cloud Scheduling**:
   - `ScheduleVideoDialog`: Added checkbox `chk_studio_schedule` ("Lên lịch trực tiếp vào TikTok Studio (Cloud Schedule)").
   - Implemented `round_to_nearest_5_minutes(minutes)` to enforce TikTok Studio's 5-minute slot boundary.
   - Enforced 15-minute minimum and 10-day maximum window constraint when in Studio mode.
   - `UploadService.execute_upload` and `UploadWorker`: Added `schedule_time` propagation directly into `SamMonnyTikTokAdapter.upload_video(..., schedule_time=schedule_time)`.
   - `MainWindow._on_schedule_videos`: If `dlg.is_studio_schedule`, immediately dispatches `UploadWorker` with the generated schedule time so that TikTok Studio accepts and stores the schedule server-side.

## Verification & Parity
- 6 new dedicated tests in `tests/unit/test_project_folders_and_studio_schedule.py`.
- 100% test suite pass rate: **129 passed in 16.50s**.
- Zero linting errors with `ruff check` and `ruff format`.
