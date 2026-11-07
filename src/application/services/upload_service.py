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

from sammonny import RemoteStatus, UploadResult

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
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.media.video_isolation import move_video_to_posted_folder
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

logger = logging.getLogger(__name__)


# Collected by the folder scan; the validation policy then rejects what the TikTok upload does not accept.
SCANNED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


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
        proxy_repo: ProxyRepository | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.video_repo = video_repo
        self.tiktok_adapter = tiktok_adapter
        self.validation_policy = validation_policy or VideoValidationPolicy()
        self.retry_policy = retry_policy or RetryPolicy()
        self.proxy_repo = proxy_repo

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
        """One folder shared by ``profile_ids``: same rules as distribute_multi_project_batches."""
        if not Path(folder_path).resolve().is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        if not profile_ids:
            return []
        return self.distribute_multi_project_batches(
            [{"project_id": None, "project_name": None, "folder_path": folder_path, "profile_ids": profile_ids}],
            min_interval_hours=min_interval_hours,
            random_order=random_order,
            prioritize_newest=prioritize_newest,
            deduplicate=deduplicate,
            caption_template=caption_template,
            privacy=privacy,
            allow_comment=allow_comment,
            allow_duet=allow_duet,
            allow_stitch=allow_stitch,
            allow_hd=allow_hd,
            is_ai_generated=is_ai_generated,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )

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
        Queues the videos of each batch's folder for that batch's profiles only. Each batch:
        ``{"project_id", "project_name", "folder_path", "profile_ids"}``.

        - files the upload would reject (validation policy: format, size) are skipped, not queued;
        - round-robin over the profiles; ``min_interval_hours`` is the gap between two videos of the SAME
          channel (channels post in parallel), counted after the videos the channel already has queued;
        - the upload options (privacy, comment/duet/stitch/HD, AI label) are stored with each video.
        """
        cancelled = cancel_token or (lambda: False)
        upload_options: dict[str, Any] = {
            "privacy": privacy,
            "allow_comment": allow_comment,
            "allow_duet": allow_duet,
            "allow_stitch": allow_stitch,
            "allow_hd": allow_hd,
            "is_ai_generated": is_ai_generated,
        }

        batch_files: list[tuple[dict[str, Any], list[Path]]] = []
        for batch in project_batches:
            folder = batch.get("folder_path")
            if not folder or not batch.get("profile_ids") or not Path(folder).resolve().is_dir():
                continue
            files = self._scan_video_files(Path(folder).resolve(), prioritize_newest, cancelled)
            if files is None:
                logger.info("Folder scan cancelled early for: %s", folder)
                return []
            batch_files.append((batch, files))

        total = sum(len(files) for _, files in batch_files)
        if total == 0:
            return []

        created: list[dict[str, Any]] = []
        processed = 0
        for batch, files in batch_files:
            if cancelled():
                break
            label = batch.get("project_name") or (
                f"Project #{batch['project_id']}" if batch.get("project_id") is not None else None
            )
            available, processed = self._collect_available_videos(
                files, deduplicate, label, processed, total, progress_callback, cancelled
            )
            if random_order:
                random.shuffle(available)
            created.extend(
                self._assign_and_register(
                    available, list(batch["profile_ids"]), min_interval_hours, caption_template, upload_options
                )
            )

        logger.info("Folder distribution completed: %d videos across %d batches", len(created), len(project_batches))
        return created

    @staticmethod
    def _scan_video_files(folder: Path, prioritize_newest: bool, cancelled: Callable[[], bool]) -> list[Path] | None:
        """Video files of ``folder`` (recursive, ``_posted``/``.posted`` excluded); None when cancelled."""
        files: list[Path] = []
        for vf in folder.rglob("*"):
            if cancelled():
                return None
            if any(part in ("_posted", ".posted") for part in vf.parts):
                continue
            if vf.is_file() and vf.suffix.lower() in SCANNED_VIDEO_EXTENSIONS:
                files.append(vf)
        if prioritize_newest:
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        else:
            files.sort(key=lambda f: f.name)
        return files

    def _collect_available_videos(
        self,
        files: list[Path],
        deduplicate: bool,
        label: str | None,
        processed: int,
        total: int,
        progress_callback: Callable[[int, int, str], None] | None,
        cancelled: Callable[[], bool],
    ) -> tuple[list[dict[str, Any]], int]:
        """Valid, not yet queued files (with hash/size/mtime) and the updated progress count."""
        available: list[dict[str, Any]] = []
        seen: set[str] = set()
        for vf in files:
            if cancelled():
                logger.info("Distribution hashing cancelled at file %d/%d", processed, total)
                break
            processed += 1
            if progress_callback:
                progress_callback(processed, total, f"[{label}] {vf.name}" if label else vf.name)

            check = self.validation_policy.validate_file(vf)
            if not check.is_valid:
                # Queueing it would only fail at upload time (after waiting for its slot).
                logger.warning("Skipping invalid video %s: %s", vf.name, check.error_message)
                continue

            file_hash = self.compute_sha256(vf)
            if deduplicate and (file_hash in seen or self.video_repo.get_by_hash(file_hash)):
                logger.info("Skipping already queued/duplicate video: %s (hash: %s)", vf.name, file_hash[:8])
                continue
            seen.add(file_hash)
            stat = vf.stat()
            available.append({"path": vf, "hash": file_hash, "size": stat.st_size, "mtime": stat.st_mtime})
        return available, processed

    def _assign_and_register(
        self,
        available: list[dict[str, Any]],
        profile_ids: list[int],
        min_interval_hours: float,
        caption_template: str | None,
        upload_options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Round-robin over ``profile_ids``; each channel's videos are ``min_interval_hours`` apart, starting
        after the channel's already queued videos (never sooner than 5 minutes from now)."""
        interval = timedelta(hours=min_interval_hours)
        earliest = datetime.now() + timedelta(minutes=5)
        next_slot: dict[int, datetime] = {}
        created: list[dict[str, Any]] = []
        for idx, item in enumerate(available):
            pid = profile_ids[idx % len(profile_ids)]
            if pid not in next_slot:
                next_slot[pid] = earliest
                latest = self.video_repo.latest_pending_schedule(pid)
                if latest:
                    try:
                        next_slot[pid] = max(earliest, datetime.fromisoformat(latest) + interval)
                    except ValueError:
                        logger.debug("Unreadable schedule_time %r for profile %s", latest, pid)
            slot = next_slot[pid]
            next_slot[pid] = slot + interval

            v_path: Path = item["path"]
            raw_title = v_path.stem.replace("_", " ").replace("-", " ")
            caption = (
                spin_caption(caption_template, title=raw_title, filename=v_path.name) if caption_template else v_path.name
            )
            sched_time = slot.strftime("%Y-%m-%d %H:%M:%S")
            vid_id = self.video_repo.register_or_update(
                video_hash=item["hash"],
                file_path=str(v_path),
                file_name=caption,
                file_size=item["size"],
                mtime=item["mtime"],
                assigned_profile_id=pid,
                schedule_time=sched_time,
                upload_options=upload_options,
            )
            created.append(
                {
                    "id": vid_id,
                    "file_path": str(v_path),
                    "file_name": caption,
                    "assigned_profile_id": pid,
                    "schedule_time": sched_time,
                    **upload_options,
                }
            )
        return created

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
                except Exception as ignored:
                    logger.debug("_safe_log: ignored error: %s", ignored)

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

                # AgentShield Strict Proxy Gate (shared egress rule): no proxy without the user's direct
                # opt-in, a leak-flagged, missing or broken proxy, or a VPN-only profile => rejected.
                from src.infrastructure.proxy.egress import EgressBlocked, resolve_profile_egress

                proxy_id = profile_row.get("proxy_id")
                px = self.proxy_repo.get_by_id(proxy_id) if (proxy_id and self.proxy_repo) else None
                try:
                    if proxy_id and self.proxy_repo and not px:
                        raise EgressBlocked(f"Proxy #{proxy_id} của hồ sơ #{profile_id} không còn tồn tại.")
                    if px is not None or not proxy_id:
                        # (proxy_id without a repository to read it: the adapter enforces the rule.)
                        resolve_profile_egress(profile_row, px)
                except EgressBlocked as blocked:
                    _safe_log("SECURITY", f"CHẶN AN TOÀN AGENTSHIELD: {blocked}", "ERROR")
                    self.video_repo.mark_error(video_id, f"Security: {blocked}")
                    raise

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
                supports_native = getattr(self.tiktok_adapter, "supports_native_schedule", None)
                if effective_schedule and callable(supports_native) and supports_native(profile_id) is False:
                    # Official API and Studio DOM ignore schedule_time (they would post NOW): keep the
                    # video for the app's own scheduler, which publishes it at the scheduled time.
                    self.video_repo.defer_to_app_schedule(video_id, profile_id, effective_schedule)
                    _safe_log(
                        "SCHEDULE",
                        f"Phương pháp upload của hồ sơ không hẹn giờ được trên TikTok: app sẽ tự đăng lúc "
                        f"{effective_schedule}",
                    )
                    return UploadResult(success=False, draft_id="", status=RemoteStatus.PENDING)

                # Explicit arguments win, then the options stored with the video when it was queued.
                def _opt(arg: bool | None, column: str, default: bool) -> bool:
                    if arg is not None:
                        return bool(arg)
                    stored = video_row.get(column)
                    return default if stored is None else bool(stored)

                eff_privacy = privacy or video_row.get("privacy") or "PUBLIC_TO_EVERYONE"
                eff_comment = _opt(allow_comment, "allow_comment", True)
                eff_duet = _opt(allow_duet, "allow_duet", True)
                eff_stitch = _opt(allow_stitch, "allow_stitch", True)
                eff_hd = _opt(allow_hd, "allow_hd", True)
                eff_ai = _opt(is_ai_generated, "is_ai_generated", False)

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
