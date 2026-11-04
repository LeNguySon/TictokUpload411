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
    clamp_caption,
    get_profile_upload_lock,
    spin_caption,
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
        """Calculates SHA-256 checksum for file deduplication."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
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
    ) -> list[dict[str, Any]]:
        """
        Scans folder for videos, filters duplicates, performs fair-share round-robin
        distribution across profile_ids, calculates staggered schedules, and registers
        drafts atomically into video_registry.
        """
        p = Path(folder_path).resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        if not profile_ids:
            return []

        valid_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        all_video_files: list[Path] = []

        for vf in p.rglob("*"):
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

        for vf in all_video_files:
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

    def execute_upload(
        self,
        video_id: int,
        profile_id: int,
        progress_callback: Callable[[int, int, float], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> UploadResult:
        """
        Atomically locks video draft for given profile, validates account readiness,
        and executes publication through the SamMonny adapter under a profile mutex.
        """
        lock = get_profile_upload_lock(profile_id)
        with lock:
            # 1. Atomic reservation to eliminate concurrency double-upload race
            reserved = self.video_repo.try_reserve(video_id=video_id, assigned_profile_id=profile_id)
            if not reserved:
                raise RuntimeError(f"Video {video_id} is already reserved or not in pending status")

            # 2. Verify Profile existence and status
            profile_row = self.profile_repo.get_by_id(profile_id)
            if not profile_row:
                raise ValueError(f"Profile {profile_id} does not exist")

            if profile_row.get("status") in ("DIE", "CHECKPOINT"):
                raise RuntimeError(f"Profile {profile_id} is in non-uploadable state: {profile_row.get('status')}")

            video_row = self.video_repo.get_by_id(video_id)
            if not video_row:
                raise ValueError(f"Video {video_id} not found")

            # 3. Publish via SamMonny Adapter with clamped caption
            try:
                raw_caption = video_row["file_name"]
                clamped_title = clamp_caption(raw_caption, max_chars=2200)
                tags = [w for w in clamped_title.split() if w.startswith("#")]

                result = self.tiktok_adapter.upload_video(
                    profile_id=profile_id,
                    video_path=video_row["file_path"],
                    title=clamped_title,
                    tags=tags,
                    privacy="PUBLIC_TO_EVERYONE",
                    allow_comment=True,
                    allow_duet=True,
                    allow_stitch=True,
                    allow_hd=True,
                    progress_callback=progress_callback,
                    cancel_token=cancel_token,
                )

                if result.success and result.publish_id:
                    logger.info("Upload succeeded! Video %s published as %s", video_id, result.publish_id)
                    self.video_repo.mark_published(
                        video_id=video_id,
                        published_profile_id=profile_id,
                        tiktok_video_id=result.publish_id,
                    )
                    try:
                        self.isolate_video_file(video_id)
                    except Exception as iso_err:
                        logger.warning("Failed to auto-isolate video %s post-upload: %s", video_id, iso_err)
                else:
                    logger.warning("Upload failed for video %s: %s", video_id, result.error)
                    self.video_repo.mark_error(video_id=video_id, error_message=result.error or "Unknown failure")

                return result

            except Exception as e:
                logger.error("Exception during upload of video %s: %s", video_id, e)
                self.video_repo.mark_error(video_id=video_id, error_message=str(e))
                raise

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
        self.video_repo.update_metadata(
            video_id=video_id,
            file_name=new_path.name,
            file_path=str(new_path),
        )
        logger.info("Video %s successfully isolated to %s and repository updated", video_id, new_path)
        return new_path
