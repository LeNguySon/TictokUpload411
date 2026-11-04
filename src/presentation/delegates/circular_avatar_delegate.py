"""
Circular Avatar Delegate for Profile Table.
Learned from Gloglin2609/ui/delegates/profile_cell_delegate.py.

Renders antialiased circular avatars at 60 FPS using an in-memory pixmap cache.
Gracefully falls back to a clean placeholder icon if no avatar is cached.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

_AVATAR_PIXMAP_CACHE: dict[str, QPixmap] = {}


def get_cached_avatar_pixmap(path_str: str, size: int) -> QPixmap | None:
    """In-memory cache for loaded QPixmaps ensuring 60 FPS smooth table scrolling."""
    if not path_str:
        return None
    cache_key = f"{path_str}_{size}"
    if cache_key in _AVATAR_PIXMAP_CACHE:
        return _AVATAR_PIXMAP_CACHE[cache_key]
    p = Path(path_str)
    if not p.exists() or not p.is_file():
        return None
    try:
        pix = QPixmap(str(p))
        if not pix.isNull():
            scaled = pix.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if len(_AVATAR_PIXMAP_CACHE) > 500:
                _AVATAR_PIXMAP_CACHE.clear()
            _AVATAR_PIXMAP_CACHE[cache_key] = scaled
            return scaled
    except Exception:
        pass
    return None


def draw_circular_avatar(painter: QPainter, pixmap: QPixmap, center: QPointF, radius: float) -> None:
    """Draws an antialiased circular avatar with a subtle border."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    path = QPainterPath()
    path.addEllipse(center, radius, radius)
    painter.setClipPath(path)

    rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
    src_rect = QRect(
        max(0, (pixmap.width() - int(radius * 2)) // 2),
        max(0, (pixmap.height() - int(radius * 2)) // 2),
        int(radius * 2),
        int(radius * 2),
    )
    painter.drawPixmap(rect.toRect(), pixmap, src_rect)

    painter.setClipping(False)
    pen = QPen(QColor(220, 224, 230, 180), 1.0)
    painter.setPen(pen)
    painter.drawEllipse(center, radius - 0.5, radius - 0.5)
    painter.restore()


class CircularAvatarDelegate(QStyledItemDelegate):
    """Custom Qt delegate rendering crisp circular avatars for TikTok MMO profiles."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def paint_avatar(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        avatar_path: str,
    ) -> None:
        """Helper to paint avatar given an explicit path or fallback."""
        rect = option.rect
        icon_size = 26
        radius = icon_size / 2.0
        center = QPointF(rect.x() + rect.width() / 2.0, rect.y() + rect.height() / 2.0)

        pixmap = get_cached_avatar_pixmap(avatar_path, icon_size * 2) if avatar_path else None
        if pixmap and not pixmap.isNull():
            draw_circular_avatar(painter, pixmap, center, radius)
        else:
            # Fallback placeholder circle
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QColor("#E2E8F0"))
            painter.setPen(QPen(QColor("#CBD5E1"), 1))
            painter.drawEllipse(center, radius, radius)

            # Draw default icon text
            painter.setPen(QColor("#64748B"))
            font = QFont("Segoe UI", 10)
            painter.setFont(font)
            painter.drawText(
                QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                Qt.AlignmentFlag.AlignCenter,
                "👤",
            )
            painter.restore()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paints the table cell with a circular avatar."""
        # Draw cell selection background
        self.initStyleOption(option, index)
        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, widget)

        # Retrieve avatar path from item data
        avatar_path = str(index.data(Qt.ItemDataRole.UserRole + 1) or index.data() or "")
        self.paint_avatar(painter, option, avatar_path)
