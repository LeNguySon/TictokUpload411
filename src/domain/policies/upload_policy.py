"""
Upload Policies & Algorithms conforming to TikTok Studio & TDS-ARCH-001 Specifications.
Inherited from battle-tested Gloglin2609 and SamMonny algorithms:
- clamp_caption: Safe hashtag-preserving text truncation for TikTok's 2200 character limit.
- spin_caption: Spintax parser and metadata placeholder injector.
- calculate_stall_timeout: Dynamic timeout scaling based on video payload size.
- get_profile_upload_lock: Thread-safe per-profile mutex preventing concurrent upload collisions.
"""

from __future__ import annotations

import logging
import random
import re
import threading

logger = logging.getLogger(__name__)

_PROFILE_UPLOAD_LOCKS: dict[int, threading.Lock] = {}
_GLOBAL_PROFILE_UPLOAD_LOCK = threading.Lock()


def get_profile_upload_lock(profile_id: int) -> threading.Lock:
    """Thread-safe per-profile mutex ensuring only one upload task accesses the account at a time."""
    with _GLOBAL_PROFILE_UPLOAD_LOCK:
        if profile_id not in _PROFILE_UPLOAD_LOCKS:
            _PROFILE_UPLOAD_LOCKS[profile_id] = threading.Lock()
        return _PROFILE_UPLOAD_LOCKS[profile_id]


def clamp_caption(caption: str, max_chars: int = 2200) -> str:
    """Safely clamp caption to TikTok Studio character limit (default 2200).

    Preserves trailing hashtags if possible, and avoids cutting words abruptly.
    """
    if not caption or len(caption) <= max_chars:
        return caption or ""

    words = caption.split(" ")
    hashtags = [w for w in words if w.startswith("#")]
    non_hashtags = [w for w in words if not w.startswith("#")]

    ht_suffix = " ".join(hashtags)
    if len(ht_suffix) > 400:
        ht_suffix = " ".join(hashtags[:10])

    allowed_body_len = max(50, max_chars - len(ht_suffix) - 5) if ht_suffix else max_chars
    body_text = " ".join(non_hashtags)

    if len(body_text) > allowed_body_len:
        truncated = body_text[:allowed_body_len]
        if " " in truncated:
            body_text = truncated.rsplit(" ", 1)[0] + "..."
        else:
            body_text = truncated + "..."

    result = f"{body_text} {ht_suffix}".strip() if ht_suffix else body_text.strip()
    if len(result) > max_chars:
        result = result[: max_chars - 3] + "..."
    return result


def spin_caption(template: str, title: str = "", filename: str = "") -> str:
    """Parses Spintax syntax {Option1|Option2|Option3} and replaces placeholders.

    Example: '{Tuyệt phẩm|Đỉnh cao} của {title} #fyp' -> 'Đỉnh cao của Video 1 #fyp'
    """
    if not template:
        return title or filename or ""

    clean_title = title or (filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ") if filename else "")
    text = template.replace("{title}", clean_title).replace("{filename}", filename)

    # Resolve nested or flat spintax blocks {a|b|c}
    pattern = re.compile(r"\{([^{}]+)\}")
    while True:
        match = pattern.search(text)
        if not match:
            break
        choices = match.group(1).split("|")
        chosen = random.choice(choices).strip()
        text = text[: match.start()] + chosen + text[match.end() :]

    return text.strip()


def calculate_stall_timeout(file_size_mb: float) -> float:
    """Calculate dynamic stall watchdog timeout based on video file size in MB.

    Gives slow residential / 4G proxies sufficient runway without premature abort.
    Min 60.0s, Max 180.0s (3 minutes).
    """
    return max(60.0, min(180.0, 60.0 + float(file_size_mb) * 0.4))
