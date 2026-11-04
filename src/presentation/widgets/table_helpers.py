"""
Presentation Table formatting helpers and canonical column definitions for Windows 11 Dual-Table UI.
"""


def get_profile_table_headers() -> list[str]:
    """Returns the exact 29-column headers (28 MMO attributes + STT) for the Profiles Table."""
    return [
        "STT",
        "Avt",
        "Tên hồ sơ",
        "Logged",
        "Proxy",
        "Type",
        "ID Tiktok",
        "Views(30d)",
        "T.Follows",
        "T.Views",
        "T.Video",
        "Email",
        "Tình trạng",
        "Cookie",
        "$Earned",
        "$Balance",
        "CS",
        "RPM",
        "QG",
        "KYC",
        "Note",
        "Re.Apply",
        "PRIVACY",
        "VAT",
        "TS",
        "STT",
        "VVP",
        "MP",
        "ID",
    ]


def get_video_table_headers() -> list[str]:
    """Returns the 14-column headers for the Video Queue Table."""
    return [
        "STT",
        "Tiêu đề",
        "Lượt view",
        "Lượt like",
        "Duration",
        "Hiển thị",
        "Lên lịch",
        "Upload To",
        "Tình trạng",
        "Source",
        "Link gốc",
        "ID Video",
        "PVF URL",
        "PAF URL",
    ]


def format_mmo_metric(val: int | float | None) -> str:
    """Formats large metric numbers with thousand separators (e.g. 2,128,959)."""
    if val is None:
        return "0"
    try:
        int_val = int(val)
        return f"{int_val:,}"
    except (ValueError, TypeError):
        return str(val)


def format_duration_string(seconds: float | int | None) -> str:
    """Formats seconds into HH:MM:SS format (e.g. 00:00:07)."""
    if seconds is None or seconds < 0:
        return "00:00:00"
    total_sec = int(seconds)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_money_string(amount: float | int | None) -> str:
    """Formats currency amount into $#,##0.00 (e.g. $1,250.50)."""
    if amount is None:
        return "$0.00"
    try:
        f_val = float(amount)
        return f"${f_val:,.2f}"
    except (ValueError, TypeError):
        return str(amount)
