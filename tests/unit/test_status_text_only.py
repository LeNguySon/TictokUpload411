"""Status column ("Tình trạng"): colored text only — no pill, border or dot — following the app theme.

The badge used to pick its palette from option.palette.base(), which is transparent in the Fluent
table, so the light app always got the dark-theme pill (dark green box, light text).
"""

from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem


def _paint_status(status: str) -> tuple[QImage, list[QColor]]:
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    table.load_profiles([{"id": 1, "name": "A", "status": status}])
    index = table.model().index(0, 12)
    delegate = table.itemDelegateForColumn(12)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 140, 38)
    option.palette = table.palette()
    img = QImage(140, 38, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    pens: list[QColor] = []
    real_set_pen = QPainter.setPen

    def spy_set_pen(self, pen):
        if isinstance(pen, QColor):
            pens.append(QColor(pen))
        return real_set_pen(self, pen)

    painter = QPainter(img)
    with (
        patch.object(QPainter, "drawRoundedRect", side_effect=AssertionError("no pill/border")),
        patch.object(QPainter, "drawEllipse", side_effect=AssertionError("no status dot")),
        patch.object(QPainter, "setPen", spy_set_pen),
    ):
        delegate.paint(painter, option, index)
    painter.end()
    table.deleteLater()
    return img, pens


def test_status_is_painted_as_colored_text_only(qtbot):
    _, pens = _paint_status("LIVE")
    assert pens, "status text must be drawn with an explicit color"


def test_status_uses_light_palette_in_light_theme(qtbot):
    from qfluentwidgets import isDarkTheme
    from src.presentation.delegates.status_badge_delegate import status_text_color

    assert not isDarkTheme()
    _, pens = _paint_status("LIVE")
    assert pens[-1].name().lower() == status_text_color("LIVE").name().lower()
    assert pens[-1].lightness() < 140, "light theme needs a dark, readable text color"


def test_each_status_has_a_distinct_color(qtbot):
    from src.presentation.delegates.status_badge_delegate import status_text_color

    colors = {status_text_color(s).name() for s in ("LIVE", "DIE", "CHECKPOINT", "running", "stopped")}
    assert len(colors) >= 4
    QApplication.processEvents()
    assert Qt.AlignmentFlag.AlignCenter  # keep import used
