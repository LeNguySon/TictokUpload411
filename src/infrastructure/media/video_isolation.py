"""
Physical Video Isolation Module: Automatically moves published videos into a _posted/ subfolder.
Prevents duplicate uploads and ensures physical isolation of published assets.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def move_video_to_posted_folder(video_path: str | Path, subfolder_name: str = "_posted") -> Path:
    """
    Physical File Isolation: Moves successfully uploaded video to `_posted/` subfolder
    co-located within the video's parent directory.
    - Creates `_posted/` if it does not exist.
    - Idempotent: If the file is already inside `subfolder_name`, returns path immediately.
    - Collision Avoidance: Resolves filename collisions by appending `_1`, `_2`...
    - Atomic move via `shutil.move`.
    """
    src = Path(video_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source video file does not exist: {video_path}")

    # Idempotent check: If file is already inside the isolation folder, no-op
    if src.parent.name == subfolder_name:
        logger.debug("Video is already in isolation directory: %s", src)
        return src

    dest_dir = src.parent / subfolder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = dest_dir / src.name
    if dest_file.exists():
        stem = src.stem
        suffix = src.suffix
        counter = 1
        while dest_file.exists():
            dest_file = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(src), str(dest_file))
    logger.info("Physically isolated video from '%s' to '%s'", src, dest_file)
    return dest_file
