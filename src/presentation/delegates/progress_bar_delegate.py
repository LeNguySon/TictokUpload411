"""
Progress bar painted by a delegate (no per-row QWidget).

One Fluent ``ProgressBar`` widget per row cost ~1 ms each to create, plus layout and its own
paint/animation per row. This delegate draws the same thin rounded Fluent bar directly in the
cell from an int (0-100) stored in ``Qt.ItemDataRole.UserRole``; updating a value repaints only
that cell.
"""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from qfluentwidgets import isDarkTheme, themeColor

PROGRESS_ROLE = Qt.ItemDataRole.UserRole
_BAR_HEIGHT = 4.0
_H_PADDING = 8.0


class ProgressBarDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Row background (hover / selection / alternate) from the table's main delegate.
        table = self.parent()
        row_delegate = getattr(table, "delegate", None)
        if row_delegate is not None:
            row_delegate.paint(painter, QStyleOptionViewItem(option), index)

        value = index.data(PROGRESS_ROLE)
        try:
            pct = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return

        rect = QRectF(option.rect).adjusted(_H_PADDING, 0, -_H_PADDING, 0)
        if rect.width() <= 0:
            return
        bar = QRectF(rect.left(), rect.center().y() - _BAR_HEIGHT / 2, rect.width(), _BAR_HEIGHT)
        radius = _BAR_HEIGHT / 2

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 40) if isDarkTheme() else QColor(0, 0, 0, 23))
        painter.drawRoundedRect(bar, radius, radius)
        if pct > 0:
            filled = QRectF(bar.left(), bar.top(), bar.width() * pct / 100.0, bar.height())
            painter.setBrush(themeColor())
            painter.drawRoundedRect(filled, radius, radius)
        painter.restore()
