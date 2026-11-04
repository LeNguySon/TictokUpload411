"""
Channel Update Worker applying batch metadata changes (Avatar, Nickname, Bio Spintax)
across selected TikTok MMO profiles on QThreadPool without blocking the GUI MainThread.
Learned from Gloglin2609/ui/views/batch_channel_update_dialog.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker
from src.domain.policies.spintax_policy import spin_text
from src.infrastructure.database.connection import db_session

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class ChannelUpdateWorker(BaseWorker):
    """Worker updating profile nickname, bio (via Spintax), and avatar in batch."""

    def __init__(
        self,
        profile_ids: list[int],
        db_path: Path | str | None = None,
        avatar_source: str | None = None,
        nickname_pattern: str | None = None,
        bio_template: str | None = None,
        signal_bus: AppSignalBus | None = None,
    ) -> None:
        super().__init__()
        self.profile_ids = profile_ids
        self.db_path = Path(db_path) if db_path else Path("data/app.db")
        self.avatar_source = avatar_source
        self.nickname_pattern = nickname_pattern
        self.bio_template = bio_template
        self.signal_bus = signal_bus or AppSignalBus.instance()

    def execute(self) -> None:
        total = len(self.profile_ids)
        if total == 0:
            return

        logger.info("Starting batch channel update for %d profiles", total)

        # Collect avatar images if source is provided
        avatar_images: list[Path] = []
        if self.avatar_source:
            src_p = Path(self.avatar_source)
            if src_p.is_file() and src_p.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                avatar_images = [src_p]
            elif src_p.is_dir():
                avatar_images = [
                    f for f in sorted(src_p.iterdir()) if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS
                ]

        for idx, pid in enumerate(self.profile_ids):
            if self.is_cancelled:
                break

            updates: dict[str, Any] = {}

            # 1. Nickname
            if self.nickname_pattern:
                nick = self.nickname_pattern.replace("{index}", str(idx + 1))
                updates["nickname"] = nick

            # 2. Bio with Spintax
            if self.bio_template:
                spun_bio = spin_text(self.bio_template)
                updates["bio"] = spun_bio

            # 3. Avatar
            if avatar_images:
                chosen_avatar = avatar_images[idx % len(avatar_images)]
                updates["avatar_path"] = str(chosen_avatar.resolve())

            if updates:
                set_clauses = [f"{k} = ?" for k in updates.keys()]
                sql = f"UPDATE profiles SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;"
                params = list(updates.values()) + [pid]
                try:
                    with db_session(self.db_path) as conn:
                        conn.execute(sql, tuple(params))
                    if self.signal_bus:
                        self.signal_bus.profile_updated.emit(pid, updates)
                except Exception as e:
                    logger.error("Failed to update profile %s in batch: %s", pid, e)

            pct = ((idx + 1) / total) * 100.0
            self.signals.progress.emit(idx + 1, total, pct)

        logger.info("Batch channel update finished for %d profiles", total)
