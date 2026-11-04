"""
Profile Domain Model representing a managed TikTok account with all 28 MMO attributes.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class ProfileStatus(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    LIVE = "LIVE"
    DIE = "DIE"
    CHECKPOINT = "CHECKPOINT"


@dataclass
class ProfileDomainModel:
    id: int
    name: str
    project_id: int | None = None
    proxy_id: int | None = None
    status: ProfileStatus = ProfileStatus.STOPPED
    username_on_tiktok: str | None = None
    views_30d: int = 0
    t_follows: int = 0
    t_views: int = 0
    t_video: int = 0
    email: str | None = None
    cookie: str | None = None
    balance: float = 0.0
    cs: str | None = None
    rpm: float = 0.0
    qg: str | None = None
    kyc: str = "No"
    note: str | None = None
    re_apply: str | None = None
    privacy: str = "PUBLIC"
    vat: str = "No"
    ts: str = "Yes"
    stt: int = 0
    vvp: int = 0
    mp: int = 0
    is_trashed: bool = False
    attributes: dict = field(default_factory=dict)

    def is_alive(self) -> bool:
        """Returns True if the account is not marked DIE or CHECKPOINT."""
        return self.status not in (ProfileStatus.DIE, ProfileStatus.CHECKPOINT)

    def is_ready_to_upload(self) -> bool:
        """Determines if the profile can be dispatched for an upload task."""
        if not self.is_alive():
            return False
        if self.is_trashed:
            return False
        return self.status in (ProfileStatus.LIVE, ProfileStatus.STOPPED)

    def mark_live(self) -> None:
        self.status = ProfileStatus.LIVE

    def mark_die(self) -> None:
        self.status = ProfileStatus.DIE

    def mark_checkpoint(self) -> None:
        self.status = ProfileStatus.CHECKPOINT
