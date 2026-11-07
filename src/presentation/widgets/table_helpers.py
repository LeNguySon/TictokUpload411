"""
Presentation Table formatting helpers and canonical column definitions for Windows 11 Dual-Table UI.
"""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QTableView, QTableWidgetItem


def h_header(table: QTableView) -> QHeaderView:
    """The table's horizontal header (Qt's stubs type it Optional; a QTableView always has one)."""
    header = table.horizontalHeader()
    assert header is not None
    return header


def v_header(table: QTableView) -> QHeaderView:
    """The table's vertical header (Qt's stubs type it Optional; a QTableView always has one)."""
    header = table.verticalHeader()
    assert header is not None
    return header


class NumericTableWidgetItem(QTableWidgetItem):
    """
    QTableWidgetItem that sorts numerically instead of lexicographically.
    Stores raw float/int for magnitude comparison while displaying formatted text.
    """

    def __init__(self, value: int | float | None, display_text: str | None = None) -> None:
        try:
            self.raw_value: float = float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            self.raw_value = 0.0

        if display_text is not None:
            text = display_text
        elif self.raw_value.is_integer():
            text = str(int(self.raw_value))
        else:
            text = str(self.raw_value)

        super().__init__(text)
        self.setData(Qt.ItemDataRole.EditRole, self.raw_value)

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self.raw_value < other.raw_value
        try:
            return self.raw_value < float(other.text().replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            return super().__lt__(other)


# Column layout version of the profile table (saved hidden columns are migrated when it changes).
PROFILE_COLUMNS_VERSION = "2"
# Last column: the database id (selection / double-click fallback).
PROFILE_COL_ID = 27
# v1 -> v2: "TS" (24, field never existed: always "Yes"), "STT" (25, duplicate of 0) and "MP" (27, field never
# existed: always 0) were replaced by real data (T.Likes, Shadowban); VVP stays 26, ID moved 28 -> 27.
_V1_TO_V2 = {**{i: i for i in range(24)}, 26: 26, 28: 27}


def migrate_hidden_profile_columns(saved: object, version: object) -> set[int]:
    """Hidden profile-table columns saved as "3,5,26" (by index), moved to the current layout."""
    hidden: set[int] = set()
    for token in str(saved or "").split(","):
        token = token.strip()
        if token.lstrip("-").isdigit():
            hidden.add(int(token))
    if str(version or "") == PROFILE_COLUMNS_VERSION:
        return hidden
    return {_V1_TO_V2[i] for i in hidden if i in _V1_TO_V2}


def get_profile_table_headers() -> list[str]:
    """Headers of the Profiles Table: every column shows real database data (no placeholder columns)."""
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
        "T.Likes",
        "Shadowban",
        "VVP",
        "ID",
    ]


def get_video_table_headers() -> list[str]:
    """Returns the 16-column headers for the Video Queue Table."""
    return [
        "STT",
        "Tiêu đề",
        "Dự Án",
        "Lượt view",
        "Lượt like",
        "Duration",
        "Hiển thị",
        "Lên lịch",
        "Upload To",
        "Tình trạng",
        "Tiến trình",
        "Nhật Ký Upload",
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


def format_duration_string(seconds: float | int | str | None) -> str:
    """Formats seconds into HH:MM:SS format (e.g. 00:00:07)."""
    if seconds is None:
        return "00:00:00"
    if isinstance(seconds, str):
        if ":" in seconds:
            return seconds
        try:
            seconds = float(seconds)
        except ValueError:
            return "00:00:00"
    if seconds < 0:
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
