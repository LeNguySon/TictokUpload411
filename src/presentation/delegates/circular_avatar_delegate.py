"""
Circular Avatar Delegate for Profile Table.
Learned from Gloglin2609/ui/delegates/profile_cell_delegate.py.

Renders antialiased circular avatars at 60 FPS using an in-memory pixmap cache.
Gracefully falls back to a clean placeholder icon if no avatar is cached.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QModelIndex, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from qfluentwidgets import isDarkTheme

_AVATAR_PIXMAP_CACHE: dict[str, QPixmap] = {}
# Paths known to be missing -> monotonic time of the check. Without this, every repaint of every
# visible row re-stat()ed the disk for avatars that are not downloaded yet (T10).
_MISSING_AVATARS: dict[str, float] = {}
MISSING_AVATAR_TTL_S = 30.0


def clear_avatar_cache() -> None:
    _AVATAR_PIXMAP_CACHE.clear()
    _MISSING_AVATARS.clear()


def forget_avatar(path_str: str) -> None:
    """Drops cached state for one avatar path (e.g. after it was downloaded or replaced)."""
    _MISSING_AVATARS.pop(path_str, None)
    for key in [k for k in _AVATAR_PIXMAP_CACHE if k.startswith(f"{path_str}_")]:
        _AVATAR_PIXMAP_CACHE.pop(key, None)


def get_cached_avatar_pixmap(path_str: str, size: int) -> QPixmap | None:
    """In-memory cache for loaded QPixmaps ensuring 60 FPS smooth table scrolling."""
    if not path_str:
        return None
    cache_key = f"{path_str}_{size}"
    if cache_key in _AVATAR_PIXMAP_CACHE:
        return _AVATAR_PIXMAP_CACHE[cache_key]
    now = time.monotonic()
    missing_since = _MISSING_AVATARS.get(path_str)
    if missing_since is not None and now - missing_since < MISSING_AVATAR_TTL_S:
        return None
    p = Path(path_str)
    if not p.is_file():
        if len(_MISSING_AVATARS) > 5000:
            _MISSING_AVATARS.clear()
        _MISSING_AVATARS[path_str] = now
        return None
    _MISSING_AVATARS.pop(path_str, None)
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


def draw_person_placeholder(painter: QPainter, center: QPointF, size: float) -> None:
    """Crisp vector "person" outline (head circle + shoulder arc), stroked in a neutral grey.

    Replaces the old "👤" emoji glyph, which is a bitmap font image and looks blurry at table size.
    """
    color = QColor("#A3A3A3") if isDarkTheme() else QColor("#7A7A7A")
    pen = QPen(color, max(1.4, size * 0.065))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Head
    head_r = size * 0.17
    painter.drawEllipse(QPointF(center.x(), center.y() - size * 0.14), head_r, head_r)
    # Shoulders: upper half of an ellipse whose ends sit near the bottom of the icon box
    shoulders = QRectF(center.x() - size * 0.39, center.y() + size * 0.05, size * 0.78, size * 0.62)
    painter.drawArc(shoulders, 0, 180 * 16)
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
            draw_person_placeholder(painter, center, float(icon_size))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paints the table cell with a circular avatar (or the vector placeholder)."""
        # Row hover/selection/alternate background shared with the rest of the row; the cell's own
        # text ("👤") must not be painted by the native item style.
        row_delegate = getattr(self.parent(), "delegate", None)
        if row_delegate is not None and hasattr(row_delegate, "paint_row_background"):
            row_delegate.paint_row_background(painter, option, index)

        # Retrieve avatar path from item data
        avatar_path = str(index.data(Qt.ItemDataRole.UserRole + 1) or index.data() or "")
        self.paint_avatar(painter, option, avatar_path)
