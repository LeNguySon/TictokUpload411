"""
Upload Application Service orchestrating atomic reservations, media validation, and SDK publishing.
"""

import hashlib
import logging
import random
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sammonny import UploadResult

from src.domain.policies.retry_policy import RetryPolicy
from src.domain.policies.upload_policy import (
    caption_from_file_name,
    clamp_caption,
    get_profile_upload_lock,
    spin_caption,
    tiktok_schedule_or_none,
)
from src.domain.policies.video_validation_policy import VideoValidationPolicy
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.media.video_isolation import move_video_to_posted_folder
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

logger = logging.getLogger(__name__)


class UploadService:
    """
    Coordinates end-to-end video preparation, atomic allocation, and publishing dispatch.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        video_repo: VideoRepository,
        tiktok_adapter: SamMonnyTikTokAdapter,
        validation_policy: VideoValidationPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.video_repo = video_repo
        self.tiktok_adapter = tiktok_adapter
        self.validation_policy = validation_policy or VideoValidationPolicy()
        self.retry_policy = retry_policy or RetryPolicy()

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Calculates SHA-256 checksum for file deduplication with 4MB buffer."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(4 * 1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()

    def enqueue_video(
        self,
        file_path: str | Path,
        title: str,
        duration_sec: float = 0.0,
        privacy: str = "PUBLIC_TO_EVERYONE",
        schedule_time: str | None = None,
        source_url: str | None = None,
        assigned_profile_id: int | None = None,
    ) -> int:
        """
        Validates the video file, calculates content hash, and registers it in the database queue.
        """
        p = Path(file_path).resolve()
        val_result = self.validation_policy.validate_file(p, duration_sec=duration_sec)
        if not val_result.is_valid:
            raise ValueError(f"Video validation failed: {val_result.error_message}")

        file_hash = self.compute_sha256(p)
        file_size = p.stat().st_size
        mtime = p.stat().st_mtime
        file_name = title or p.name

        return self.video_repo.register_or_update(
            video_hash=file_hash,
            file_path=str(p),
            file_name=file_name,
            file_size=file_size,
            mtime=mtime,
            schedule_time=schedule_time,
            assigned_profile_id=assigned_profile_id,
        )

    def distribute_folder_videos_to_queue(
        self,
        folder_path: str | Path,
        profile_ids: list[int],
        min_interval_hours: float = 12.0,
        random_order: bool = False,
        prioritize_newest: bool = True,
        deduplicate: bool = True,
        caption_template: str | None = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        allow_hd: bool = True,
        is_ai_generated: bool = False,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scans folder for videos, filters duplicates, performs fair-share round-robin
        distribution across profile_ids, calculates staggered schedules, and registers
        drafts atomically into video_registry.
        Supports async progress reporting and cooperative cancellation.
        """
        p = Path(folder_path).resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        if not profile_ids:
            return []

        valid_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        all_video_files: list[Path] = []

        for vf in p.rglob("*"):
            if cancel_token and cancel_token():
                logger.info("Folder scan cancelled early for: %s", folder_path)
                return []
            if any(part in ("_posted", ".posted") for part in vf.parts):
                continue
            if vf.is_file() and vf.suffix.lower() in valid_extensions:
                all_video_files.append(vf)

        if not all_video_files:
            logger.info("No video files found in folder: %s", folder_path)
            return []

        # Sort order
        if prioritize_newest:
            all_video_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        else:
            all_video_files.sort(key=lambda f: f.name)

        # Deduplication filtering
        available_videos: list[dict[str, Any]] = []
        seen_in_batch: set[str] = set()
        total_files = len(all_video_files)

        for idx, vf in enumerate(all_video_files, start=1):
            if cancel_token and cancel_token():
                logger.info("Distribution hashing cancelled at file %d/%d", idx, total_files)
                break
            if progress_callback:
                progress_callback(idx, total_files, vf.name)

            file_hash = self.compute_sha256(vf)
            if deduplicate:
                existing = self.video_repo.get_by_hash(file_hash)
                if existing:
                    logger.info("Skipping already claimed/indexed video: %s (hash: %s)", vf.name, file_hash[:8])
                    continue
                if file_hash in seen_in_batch:
                    logger.info("Skipping duplicate video within same batch: %s", vf.name)
                    continue

            seen_in_batch.add(file_hash)
            available_videos.append(
                {
                    "path": vf,
                    "hash": file_hash,
                    "size": vf.stat().st_size,
                    "mtime": vf.stat().st_mtime,
                }
            )

        if not available_videos:
            logger.info("No available videos left after deduplication: %s", folder_path)
            return []

        if random_order:
            random.shuffle(available_videos)

        created_items: list[dict[str, Any]] = []
        now = datetime.now()

        for idx, item in enumerate(available_videos):
            target_profile_id = profile_ids[idx % len(profile_ids)]
            v_path: Path = item["path"]
            raw_title = v_path.stem.replace("_", " ").replace("-", " ")

            if caption_template:
                final_caption = spin_caption(caption_template, title=raw_title, filename=v_path.name)
            else:
                final_caption = v_path.name

            # Calculate schedule slot
            slot_offset_min = 5 + int(idx * (min_interval_hours * 60))
            sched_time = (now + timedelta(minutes=slot_offset_min)).strftime("%Y-%m-%d %H:%M:%S")

            vid_id = self.video_repo.register_or_update(
                video_hash=item["hash"],
                file_path=str(v_path),
                file_name=final_caption,
                file_size=item["size"],
                mtime=item["mtime"],
                assigned_profile_id=target_profile_id,
                schedule_time=sched_time,
            )

            created_items.append(
                {
                    "id": vid_id,
                    "file_path": str(v_path),
                    "file_name": final_caption,
                    "assigned_profile_id": target_profile_id,
                    "schedule_time": sched_time,
                    "privacy": privacy,
                    "allow_comment": allow_comment,
                    "allow_duet": allow_duet,
                    "allow_stitch": allow_stitch,
                    "allow_hd": allow_hd,
                    "is_ai_generated": is_ai_generated,
                }
            )

        logger.info(
            "Distributed %d videos across %d profiles from folder: %s",
            len(created_items),
            len(profile_ids),
            folder_path,
        )
        return created_items

    def distribute_multi_project_batches(
        self,
        project_batches: list[dict[str, Any]],
        min_interval_hours: float = 12.0,
        random_order: bool = False,
        prioritize_newest: bool = True,
        deduplicate: bool = True,
        caption_template: str | None = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        allow_hd: bool = True,
        is_ai_generated: bool = False,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Distributes video folders across multiple projects concurrently.
        Each project batch contains:
          - 'project_id': int
          - 'project_name': str
          - 'folder_path': str | Path
          - 'profile_ids': list[int]
        Fair-share distribution ensures videos from a project's folder are only
        assigned to profiles within that project.
        """
        all_created_items: list[dict[str, Any]] = []
        valid_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        total_files_across_projects = 0
        batch_file_maps: list[tuple[dict[str, Any], list[Path]]] = []

        for batch in project_batches:
            f_path_str = batch.get("folder_path")
            if not f_path_str:
                continue
            f_path = Path(f_path_str).resolve()
            if not f_path.is_dir() or not batch.get("profile_ids"):
                continue

            v_files: list[Path] = []
            for vf in f_path.rglob("*"):
                if cancel_token and cancel_token():
                    return []
                if any(part in ("_posted", ".posted") for part in vf.parts):
                    continue
                if vf.is_file() and vf.suffix.lower() in valid_extensions:
                    v_files.append(vf)

            if prioritize_newest:
                v_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            else:
                v_files.sort(key=lambda f: f.name)

            total_files_across_projects += len(v_files)
            batch_file_maps.append((batch, v_files))

        if total_files_across_projects == 0:
            return []

        processed_so_far = 0

        for batch, v_files in batch_file_maps:
            if cancel_token and cancel_token():
                break

            proj_name = batch.get("project_name") or f"Project #{batch.get('project_id')}"
            profile_ids = batch["profile_ids"]

            seen_in_batch: set[str] = set()
            available_videos: list[dict[str, Any]] = []

            for vf in v_files:
                if cancel_token and cancel_token():
                    break

                processed_so_far += 1
                if progress_callback:
                    progress_callback(processed_so_far, total_files_across_projects, f"[{proj_name}] {vf.name}")

                file_hash = self.compute_sha256(vf)
                if deduplicate:
                    existing = self.video_repo.get_by_hash(file_hash)
                    if existing:
                        continue
                    if file_hash in seen_in_batch:
                        continue

                seen_in_batch.add(file_hash)
                available_videos.append(
                    {
                        "path": vf,
                        "hash": file_hash,
                        "size": vf.stat().st_size,
                        "mtime": vf.stat().st_mtime,
                    }
                )

            if not available_videos:
                continue

            if random_order:
                random.shuffle(available_videos)

            now = datetime.now()
            for idx, item in enumerate(available_videos):
                target_profile_id = profile_ids[idx % len(profile_ids)]
                v_path: Path = item["path"]
                raw_title = v_path.stem.replace("_", " ").replace("-", " ")

                if caption_template:
                    final_caption = spin_caption(caption_template, title=raw_title, filename=v_path.name)
                else:
                    final_caption = v_path.name

                slot_offset_min = 5 + int(idx * (min_interval_hours * 60))
                sched_time = (now + timedelta(minutes=slot_offset_min)).strftime("%Y-%m-%d %H:%M:%S")

                vid_id = self.video_repo.register_or_update(
                    video_hash=item["hash"],
                    file_path=str(v_path),
                    file_name=final_caption,
                    file_size=item["size"],
                    mtime=item["mtime"],
                    assigned_profile_id=target_profile_id,
                    schedule_time=sched_time,
                )

                all_created_items.append(
                    {
                        "id": vid_id,
                        "file_path": str(v_path),
                        "file_name": final_caption,
                        "assigned_profile_id": target_profile_id,
                        "schedule_time": sched_time,
                        "privacy": privacy,
                        "allow_comment": allow_comment,
                        "allow_duet": allow_duet,
                        "allow_stitch": allow_stitch,
                        "allow_hd": allow_hd,
                        "is_ai_generated": is_ai_generated,
                    }
                )

        logger.info(
            "Multi-project batch distribution completed: %d videos across %d projects",
            len(all_created_items),
            len(project_batches),
        )
        return all_created_items

    def execute_upload(
        self,
        video_id: int,
        profile_id: int,
        privacy: str | None = None,
        allow_comment: bool | None = None,
        allow_duet: bool | None = None,
        allow_stitch: bool | None = None,
        allow_hd: bool | None = None,
        is_ai_generated: bool | None = None,
        schedule_time: str | None = None,
        progress_callback: Callable[[int, int, float], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
        log_callback: Callable[..., None] | None = None,
    ) -> UploadResult:
        """
        Atomically locks video draft for given profile, validates account readiness,
        and executes publication through the SamMonny adapter under a profile mutex.
        If schedule_time is provided (or preset on video), it passes it to the adapter
        for native TikTok Studio Cloud scheduling.
        Supports custom privacy, interactive flags (comment, duet, stitch, hd), and AI content declaration.
        """

        def _safe_log(stage: str, msg: str, level: str = "INFO") -> None:
            if log_callback:
                try:
                    log_callback(stage, msg, level)
                except TypeError:
                    log_callback(stage, msg)
                except Exception:
                    pass

        lock = get_profile_upload_lock(profile_id)
        with lock:
            # 1. Profile must exist before anything is written (a bogus id would also violate the FK).
            profile_row = self.profile_repo.get_by_id(profile_id)
            if not profile_row:
                _safe_log("PROFILE", f"Không tìm thấy hồ sơ #{profile_id}", "ERROR")
                raise ValueError(f"Profile {profile_id} does not exist")

            # 2. Atomic claim -> 'uploading'. Honours the scheduler's reservation for this profile and
            #    allows an explicit retry of a failed video; never steals an in-flight/published one.
            if not self.video_repo.claim_for_upload(video_id=video_id, profile_id=profile_id):
                _safe_log("RESERVE", f"Thất bại: Video #{video_id} đã được khóa bởi tiến trình khác", "ERROR")
                raise RuntimeError(f"Video {video_id} is already being uploaded, published or reserved")

            _safe_log("RESERVE", f"Đã khóa draft Video #{video_id} thành công cho Profile #{profile_id}")

            # From here on we own the video: every failure must leave it 'failed', never stuck.
            try:
                p_title = (
                    profile_row.get("channel_title") or profile_row.get("account_name") or f"Profile #{profile_id}"
                )
                _safe_log(
                    "PROFILE", f"Xác thực Kênh TikTok: {p_title} (Trạng thái: {profile_row.get('status', 'ACTIVE')})"
                )
                if profile_row.get("status") in ("DIE", "CHECKPOINT"):
                    _safe_log(
                        "PROFILE",
                        f"Kênh #{profile_id} đang ở trạng thái không thể đăng: {profile_row.get('status')}",
                        "ERROR",
                    )
                    raise RuntimeError(f"Profile {profile_id} is in non-uploadable state: {profile_row.get('status')}")

                video_row = self.video_repo.get_by_id(video_id)
                if not video_row:
                    _safe_log("VALIDATE", f"Không tìm thấy thông tin video #{video_id}", "ERROR")
                    raise ValueError(f"Video {video_id} not found")

                # 3. Publish via SamMonny Adapter with clamped caption
                raw_caption = caption_from_file_name(video_row["file_name"])
                clamped_title = clamp_caption(raw_caption, max_chars=2200)
                tags = [w for w in clamped_title.split() if w.startswith("#")]
                requested_schedule = schedule_time if schedule_time is not None else video_row.get("schedule_time")
                # Past/due times (auto-dispatch) or times outside TikTok's window publish immediately.
                effective_schedule = tiktok_schedule_or_none(requested_schedule)
                if requested_schedule and not effective_schedule:
                    _safe_log("SCHEDULE", f"Lịch {requested_schedule} đã tới hạn/ngoài khung TikTok: đăng ngay")

                eff_privacy = privacy or video_row.get("privacy") or "PUBLIC_TO_EVERYONE"
                eff_comment = allow_comment if allow_comment is not None else video_row.get("allow_comment", True)
                eff_duet = allow_duet if allow_duet is not None else video_row.get("allow_duet", True)
                eff_stitch = allow_stitch if allow_stitch is not None else video_row.get("allow_stitch", True)
                eff_hd = allow_hd if allow_hd is not None else video_row.get("allow_hd", True)
                eff_ai = is_ai_generated if is_ai_generated is not None else video_row.get("is_ai_generated", False)

                file_size_mb = (video_row.get("file_size") or 0) / (1024 * 1024)
                _safe_log("VALIDATE", f"Tệp video: {video_row.get('file_path')} ({file_size_mb:.1f} MB)")
                _safe_log("PUBLISH", f"Đang gửi dữ liệu đăng lên TikTok Studio (Quyền riêng tư: {eff_privacy})")

                result = self.tiktok_adapter.upload_video(
                    profile_id=profile_id,
                    video_path=video_row["file_path"],
                    title=clamped_title,
                    tags=tags,
                    privacy=eff_privacy,
                    allow_comment=eff_comment,
                    allow_duet=eff_duet,
                    allow_stitch=eff_stitch,
                    allow_hd=eff_hd,
                    is_ai_generated=eff_ai,
                    schedule_time=effective_schedule,
                    progress_callback=progress_callback,
                    cancel_token=cancel_token,
                )
            except Exception as e:
                logger.error("Exception during upload of video %s: %s", video_id, e)
                self.video_repo.mark_error(video_id=video_id, error_message=str(e))
                raise

            if result.success:
                # Some modes (cookie hybrid, native scheduling) succeed without returning an id; it is
                # still published - recording it as failed would invite a duplicate re-upload.
                logger.info("Upload succeeded! Video %s published as %s", video_id, result.publish_id)
                self.video_repo.mark_published(
                    video_id=video_id,
                    published_profile_id=profile_id,
                    tiktok_video_id=result.publish_id or "",
                )
                _safe_log(
                    "ISOLATE",
                    f"Đã xuất bản thành công (ID: {result.publish_id or 'chưa trả về'}). Tiến hành cách ly video...",
                )
                try:
                    self.isolate_video_file(video_id)
                    _safe_log("ISOLATE", "Cách ly vật lý video vào thư mục _posted/ hoàn tất")
                except Exception as iso_err:
                    logger.warning("Failed to auto-isolate video %s post-upload: %s", video_id, iso_err)
                    _safe_log("ISOLATE", f"Cảnh báo cách ly video: {iso_err}", "WARNING")
            elif result.is_ambiguous:
                # Sent but not confirmed (e.g. timeout after the upload): keep it 'uploading' so it is not
                # retried automatically; it needs reconciliation, otherwise a retry may post it twice.
                logger.warning("Upload of video %s is ambiguous, left 'uploading': %s", video_id, result.error)
                _safe_log(
                    "ERROR",
                    f"Chưa xác nhận được kết quả đăng ({result.error or 'không rõ'}). "
                    "Video giữ trạng thái 'uploading' để tránh đăng trùng - hãy kiểm tra trên TikTok.",
                    "WARNING",
                )
            else:
                logger.warning("Upload failed for video %s: %s", video_id, result.error)
                self.video_repo.mark_error(video_id=video_id, error_message=result.error or "Unknown failure")
                _safe_log("ERROR", f"Tải lên thất bại: {result.error or 'Lỗi không xác định'}", "ERROR")

            return result

    def isolate_video_file(self, video_id: int, subfolder_name: str = "_posted") -> Path | None:
        """
        Physically isolates video into _posted/ subfolder and updates database metadata.
        Returns the resolved new Path, or None if the record/file does not exist.
        """
        video_row = self.video_repo.get_by_id(video_id)
        if not video_row or not video_row.get("file_path"):
            logger.warning("Video %s not found in repository for isolation", video_id)
            return None

        src_path = Path(video_row["file_path"])
        if not src_path.is_file():
            logger.warning("Physical video file for video %s does not exist: %s", video_id, src_path)
            return None

        new_path = move_video_to_posted_folder(src_path, subfolder_name=subfolder_name)
        # Only the path changes: file_name holds the caption and must survive isolation.
        self.video_repo.update_metadata(video_id=video_id, file_path=str(new_path))
        logger.info("Video %s successfully isolated to %s and repository updated", video_id, new_path)
        return new_path
