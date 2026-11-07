"""Time zone sent with TikTok analytics requests.

TikTok returns hourly analytics (follower active hours, view history...) in the ``tz_offset`` / ``time_offset`` the
request sends (seconds east of UTC). The app schedules posts on the machine's own clock, so the requests must send
the machine's current UTC offset (it was hard-coded to 25200 = UTC+7: wrong best hours on any other machine).
"""

from __future__ import annotations

from datetime import datetime


def _local_now() -> datetime:
    return datetime.now().astimezone()


def local_utc_offset_seconds() -> int:
    """The machine's current UTC offset in seconds (DST included), e.g. 25200 for UTC+7, -21600 for UTC-6."""
    offset = _local_now().utcoffset()
    return int(offset.total_seconds()) if offset is not None else 0
