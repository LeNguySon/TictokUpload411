"""
Upload Application Service orchestrating atomic reservations, media validation, and SDK publishing.
"""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from sammonny import UploadResult

from src.domain.policies.retry_policy import RetryPolicy
from src.domain.policies.video_validation_policy import VideoValidationPolicy
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
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
        )

    def execute_upload(
        self,
        video_id: int,
        profile_id: int,
        progress_callback: Callable[[int, int, float], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> UploadResult:
        """
        Atomically locks video draft for given profile, validates account readiness,
        and executes publication through the SamMonny adapter.
        """
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

        # 3. Publish via SamMonny Adapter
        try:
            result = self.tiktok_adapter.upload_video(
                profile_id=profile_id,
                video_path=video_row["file_path"],
                title=video_row["file_name"],
                privacy="PUBLIC_TO_EVERYONE",
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
            else:
                logger.warning("Upload failed for video %s: %s", video_id, result.error)
                self.video_repo.mark_error(video_id=video_id, error_message=result.error or "Unknown failure")

            return result

        except Exception as e:
            logger.error("Exception during upload of video %s: %s", video_id, e)
            self.video_repo.mark_error(video_id=video_id, error_message=str(e))
            raise
