"""
StatusBadgeDelegate — Modern rounded pill badges with glowing dots and high-contrast labels.
Learned from Gloglin2609/ui/delegates/status_delegate.py and aligned with Windows 11 Fluent Design.
Eliminates text elision / 'stop...' truncation permanently.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QModelIndex, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from qfluentwidgets import isDarkTheme

# Badge styling: (bg_light, border_light, text_light, dot_light, bg_dark, border_dark, text_dark, dot_dark, label)
STATUS_THEMES: dict[str, tuple[str, str, str, str, str, str, str, str, str]] = {
    "stopped": (
        "#ECFDF5",
        "#A7F3D0",
        "#065F46",
        "#10B981",
        "#064E3B",
        "#059669",
        "#A7F3D0",
        "#34D399",
        "Sẵn sàng",
    ),
    "ready": (
        "#ECFDF5",
        "#A7F3D0",
        "#065F46",
        "#10B981",
        "#064E3B",
        "#059669",
        "#A7F3D0",
        "#34D399",
        "Sẵn sàng",
    ),
    "launching": (
        "#FFFBEB",
        "#FDE68A",
        "#B45309",
        "#F59E0B",
        "#78350F",
        "#F59E0B",
        "#FDE68A",
        "#FBBF24",
        "Đang mở...",
    ),
    "running": (
        "#EFF6FF",
        "#BFDBFE",
        "#1E40AF",
        "#3B82F6",
        "#1E3A8A",
        "#3B82F6",
        "#BFDBFE",
        "#60A5FA",
        "Đang mở",
    ),
    "live": (
        "#E6F9EE",
        "#86EFAC",
        "#15803D",
        "#22C55E",
        "#14532D",
        "#22C55E",
        "#BBF7D0",
        "#4ADE80",
        "LIVE",
    ),
    "die": (
        "#FEF2F2",
        "#FECACA",
        "#991B1B",
        "#EF4444",
        "#7F1D1D",
        "#DC2626",
        "#FECACA",
        "#F87171",
        "DIE",
    ),
    "checkpoint": (
        "#FFF7ED",
        "#FED7AA",
        "#C2410C",
        "#F97316",
        "#7C2D12",
        "#EA580C",
        "#FFEDD5",
        "#FB923C",
        "CHECKPOINT",
    ),
    "checking": (
        "#FFFBEB",
        "#FDE68A",
        "#92400E",
        "#F59E0B",
        "#78350F",
        "#D97706",
        "#FDE68A",
        "#FBBF24",
        "Đang kiểm tra",
    ),
    "error": (
        "#FEF2F2",
        "#FECACA",
        "#991B1B",
        "#EF4444",
        "#7F1D1D",
        "#DC2626",
        "#FECACA",
        "#F87171",
        "Lỗi",
    ),
}


def get_status_config(status_raw: Any, is_light: bool = True) -> tuple[str, str, str, str, str]:
    """Resolves status key into concrete hex colors and localized label for current palette."""
    st = str(status_raw or "ready").strip().lower()
    cfg = STATUS_THEMES.get(st, STATUS_THEMES["ready"])
    if is_light:
        return cfg[0], cfg[1], cfg[2], cfg[3], cfg[8]
    return cfg[4], cfg[5], cfg[6], cfg[7], cfg[8]


def status_text_color(status_raw: Any) -> QColor:
    """Readable text color of a status for the current Fluent theme (light app -> dark tones)."""
    _, _, text_col, _, _ = get_status_config(status_raw, is_light=not isDarkTheme())
    return QColor(text_col)


class StatusBadgeDelegate(QStyledItemDelegate):
    """
    Paints the status as colored text only (no pill, border or dot), centered in the cell.
    Row hover/selection backgrounds come from the table's own delegate so the column matches the rest
    of the row. The theme comes from qfluentwidgets: the Fluent table palette's base color is
    transparent, so palette-based detection always picked the dark palette in the light app.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        row_delegate = getattr(self.parent(), "delegate", None)
        if row_delegate is not None and hasattr(row_delegate, "paint_row_background"):
            row_delegate.paint_row_background(painter, option, index)

        user_data = index.data(Qt.ItemDataRole.UserRole)
        display_data = index.data(Qt.ItemDataRole.DisplayRole)
        status_key = user_data if user_data is not None else display_data
        label_text = get_status_config(status_key)[4]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(status_text_color(status_key))
        painter.drawText(QRectF(option.rect), int(Qt.AlignmentFlag.AlignCenter), label_text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(125, 34)


__all__ = ["STATUS_THEMES", "StatusBadgeDelegate", "get_status_config", "status_text_color"]
