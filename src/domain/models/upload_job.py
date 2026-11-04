"""
Upload Job Domain Model representing an asynchronous video publishing job.
"""

import time
from dataclasses import dataclass
from enum import StrEnum


class UploadJobStatus(StrEnum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class UploadExecutionMode(StrEnum):
    OFFICIAL_DIRECT_POST = "official_direct_post"
    COOKIE_API_HYBRID = "cookie_api_hybrid"
    HEADLESS_STUDIO = "headless_studio"
    MANUAL_HANDOFF = "manual_handoff"


@dataclass
class UploadJobDomainModel:
    job_id: str
    video_id: int
    profile_id: int
    mode: UploadExecutionMode
    status: UploadJobStatus = UploadJobStatus.QUEUED
    retry_count: int = 0
    max_retries: int = 3
    publish_id: str | None = None
    last_error: str | None = None
    created_at: float = 0.0
    completed_at: float | None = None

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            self.created_at = time.time()

    def mark_in_progress(self) -> None:
        self.status = UploadJobStatus.IN_PROGRESS

    def record_failure(self, error_msg: str, retryable: bool) -> None:
        self.last_error = error_msg
        if retryable and self.retry_count < self.max_retries:
            self.retry_count += 1
            self.status = UploadJobStatus.RETRYING
        else:
            self.status = UploadJobStatus.FAILED

    def mark_completed(self, publish_id: str) -> None:
        self.status = UploadJobStatus.COMPLETED
        self.publish_id = publish_id
        self.completed_at = time.time()
