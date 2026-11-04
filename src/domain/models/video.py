"""
Video Draft Domain Model representing local video media, publishing parameters, and deduplication state.
"""

from dataclasses import dataclass
from enum import StrEnum


class VideoStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    ERROR = "error"


class PrivacyLevel(StrEnum):
    PUBLIC_TO_EVERYONE = "PUBLIC_TO_EVERYONE"
    MUTUAL_FOLLOW_FRIENDS = "MUTUAL_FOLLOW_FRIENDS"
    SELF_ONLY = "SELF_ONLY"


@dataclass
class VideoDraftDomainModel:
    id: int
    file_path: str
    file_hash: str
    title: str
    duration_seconds: float = 0.0
    view_count: int = 0
    like_count: int = 0
    privacy_level: PrivacyLevel = PrivacyLevel.PUBLIC_TO_EVERYONE
    is_scheduled: bool = False
    schedule_time: str | None = None
    upload_to_profile_id: int | None = None
    status: VideoStatus = VideoStatus.PENDING
    download_progress: int = 100
    source_url: str | None = None
    last_error: str | None = None

    def can_be_assigned(self) -> bool:
        """Video can only be assigned if currently pending without active profile."""
        return self.status == VideoStatus.PENDING and self.upload_to_profile_id is None

    def assign_to_profile(self, profile_id: int) -> None:
        if not self.can_be_assigned():
            raise ValueError(f"Cannot assign video {self.id} with status {self.status}")
        self.upload_to_profile_id = profile_id
        self.status = VideoStatus.ASSIGNED

    def release_assignment(self) -> None:
        self.upload_to_profile_id = None
        self.status = VideoStatus.PENDING
