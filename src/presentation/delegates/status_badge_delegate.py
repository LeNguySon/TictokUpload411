"""
StatusBadgeDelegate — Modern rounded pill badges with glowing dots and high-contrast labels.
Learned from Gloglin2609/ui/delegates/status_delegate.py and aligned with Windows 11 Fluent Design.
Eliminates text elision / 'stop...' truncation permanently.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QModelIndex, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

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


class StatusBadgeDelegate(QStyledItemDelegate):
    """
    Paints a modern rounded pill status badge matching enterprise antidetect dashboards.
    Prevents text elision ('stop...') by computing explicit geometry with sub-pixel antialiasing.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = option.rect

        is_light = option.palette.base().color().lightness() > 128

        # Background row hover / selection highlight
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor("#E0F2FE" if is_light else "#1E293B"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor("#F8FAFC" if is_light else "#1A2234"))

        # Extract status key
        user_data = index.data(Qt.ItemDataRole.UserRole)
        display_data = index.data(Qt.ItemDataRole.DisplayRole)
        status_key = user_data if user_data is not None else display_data

        bg_col, border_col, text_col, dot_col, label_text = get_status_config(status_key, is_light=is_light)

        # Compute pill width adaptively based on label length
        pill_w = 104.0 if len(label_text) >= 8 else 92.0
        pill_h = 24.0

        # Perfectly center pill inside the table cell
        pill_x = float(rect.x() + max(4.0, (rect.width() - pill_w) / 2))
        pill_y = float(rect.y() + (rect.height() - pill_h) / 2)
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        # 1. Draw Pill Background & Border
        painter.setPen(QPen(QColor(border_col), 1.0))
        painter.setBrush(QColor(bg_col))
        painter.drawRoundedRect(pill_rect, 12.0, 12.0)

        # 2. Draw Glowing Status Dot
        dot_r = 3.5
        dot_cx = pill_x + 11.0
        dot_cy = pill_y + (pill_h / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(dot_col))
        painter.drawEllipse(QRectF(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2))

        # 3. Draw Localized Text Label
        font = QFont("Segoe UI", 9)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(text_col))

        # Text area offset right from the dot
        text_rect = QRectF(pill_x + 18.0, pill_y, pill_w - 22.0, pill_h)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter),
            label_text,
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(125, 34)


__all__ = ["STATUS_THEMES", "StatusBadgeDelegate", "get_status_config"]
