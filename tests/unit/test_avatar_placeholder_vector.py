"""Avatar placeholder: crisp vector person outline (head circle + shoulder arc), no emoji glyph.

The old placeholder printed the "👤" emoji (a bitmap font glyph, blurry when scaled) on a filled
circle, and the cell's own "👤" text could be painted underneath by the native item style.
"""

from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionViewItem


def _paint_avatar_cell(avatar_path: str = ""):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    table.load_profiles([{"id": 1, "name": "A", "avatar_path": avatar_path}])
    index = table.model().index(0, 1)
    delegate = table.itemDelegateForColumn(1)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 38)
    option.palette = table.palette()
    img = QImage(40, 38, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)
    with (
        patch.object(QPainter, "drawText", side_effect=AssertionError("no emoji/text glyph in the avatar cell")),
        patch.object(QPainter, "drawEllipse", wraps=painter.drawEllipse) as ellipse,
        patch.object(QPainter, "drawArc", wraps=painter.drawArc) as arc,
    ):
        delegate.paint(painter, option, index)
    painter.end()
    table.deleteLater()
    return img, ellipse, arc


def test_placeholder_is_a_vector_person_outline(qtbot):
    img, ellipse, arc = _paint_avatar_cell("")
    assert ellipse.called, "head circle"
    assert arc.called, "shoulder arc"


def test_placeholder_has_no_filled_background_disc(qtbot):
    img, _, _ = _paint_avatar_cell("")
    # Point between head and shoulders, off the strokes: must stay the cell background (no grey disc).
    assert img.pixelColor(20 - 9, 19 + 9).lightness() > 240
