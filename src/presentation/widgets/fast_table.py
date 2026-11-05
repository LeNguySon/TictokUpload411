"""
Fast Fluent table: same look as qfluentwidgets.TableWidget, without its full-viewport repaints.

qfluentwidgets' TableBase calls ``viewport().update()`` on every hover-row, pressed-row and
selection change and paints every cell through a heavy Python delegate. With ~470 visible cells
that is ~130 ms per mouse move/click. This module keeps the Fluent visuals but:

- repaints only the rows whose hover/pressed/selected state actually changed;
- derives selected rows from selection ranges instead of ``selectedIndexes()`` (O(rows x cols));
- paints cells with a lean delegate (cached font, no per-cell painter save/restore for plain cells).
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QModelIndex, QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPalette
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTableView, QTableWidgetItem
from qfluentwidgets import TableWidget, isDarkTheme
from qfluentwidgets.common.font import getFont
from qfluentwidgets.components.widgets.table_view import TableItemDelegate

# Above this many changed rows a single full repaint is cheaper than many row rects.
_FULL_REPAINT_THRESHOLD = 24


class FastTableItemDelegate(TableItemDelegate):
    """Drop-in replacement for Fluent's TableItemDelegate with a cheaper paint path."""

    def __init__(self, parent: QTableView) -> None:
        super().__init__(parent)
        self._font = getFont(13)

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: N802
        QStyledItemDelegate.initStyleOption(self, option, index)
        option.font = index.data(Qt.ItemDataRole.FontRole) or self._font

        text_color = QColor(Qt.GlobalColor.white if isDarkTheme() else Qt.GlobalColor.black)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if brush is not None:
            text_color = QBrush(brush).color()
        option.palette.setColor(QPalette.ColorRole.Text, text_color)
        option.palette.setColor(QPalette.ColorRole.HighlightedText, text_color)

    def _background_alpha(self, row: int, is_dark: bool) -> int:
        if row in self.selectedRows:
            if row == self.pressedRow:
                return 15 if is_dark else 9
            return 25 if row == self.hoverRow else 17
        if row == self.pressedRow:
            return 9 if is_dark else 6
        if row == self.hoverRow:
            return 12
        if row % 2 == 0 and self.parent().alternatingRowColors():
            return 5
        return 0

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            # Rare (check-box columns): keep Fluent's full implementation.
            super().paint(painter, option, index)
            return

        row, col = index.row(), index.column()
        option.rect.adjust(0, self.margin, 0, -self.margin)

        background = index.data(Qt.ItemDataRole.BackgroundRole)
        is_dark = isDarkTheme()
        alpha = self._background_alpha(row, is_dark)
        if background is not None or alpha:
            if background is not None:
                brush = QBrush(background)
            else:
                c = 255 if is_dark else 0
                brush = QBrush(QColor(c, c, c, alpha))
            last_col = index.model().columnCount(index.parent()) - 1
            if col == 0 or col == last_col:
                painter.save()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setClipRect(option.rect.adjusted(0, -self.margin, 0, self.margin))
                painter.setBrush(brush)
                self._drawBackground(painter, option, index)
                if col == 0 and row in self.selectedRows and self.parent().horizontalScrollBar().value() == 0:
                    self._drawIndicator(painter, option, index)
                painter.restore()
            else:
                painter.fillRect(option.rect, brush)  # exact cell rect: overlap would double the alpha at seams

        QStyledItemDelegate.paint(self, painter, option, index)


class FastTableWidget(TableWidget):
    """Fluent TableWidget that repaints only rows whose visual state changed."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(FastTableItemDelegate(self))

    # -- partial repaint helpers ------------------------------------------------
    def _row_rect(self, row: int) -> QRect | None:
        if row < 0 or row >= self.rowCount():
            return None
        y = self.rowViewportPosition(row)
        if y < 0 and y + self.rowHeight(row) < 0:
            return None
        return QRect(0, y, self.viewport().width(), self.rowHeight(row))

    def _update_rows(self, rows: set[int]) -> None:
        rows = {r for r in rows if r >= 0}
        if not rows:
            return
        if len(rows) > _FULL_REPAINT_THRESHOLD:
            self.viewport().update()
            return
        for r in rows:
            rect = self._row_rect(r)
            if rect is not None:
                self.viewport().update(rect)

    # -- Fluent TableBase overrides --------------------------------------------
    def _setHoverRow(self, row: int) -> None:  # noqa: N802
        old = self.delegate.hoverRow
        if old == row:
            return
        self.delegate.setHoverRow(row)
        self._update_rows({old, row})

    def _setPressedRow(self, row: int) -> None:  # noqa: N802
        if self.selectionMode() == QTableView.SelectionMode.NoSelection:
            return
        old = self.delegate.pressedRow
        if old == row:
            return
        self.delegate.setPressedRow(row)
        self._update_rows({old, row})

    def _selected_row_set(self) -> set[int]:
        model = self.selectionModel()
        if model is None:
            return set()
        rows: set[int] = set()
        for rng in model.selection():
            rows.update(range(rng.top(), rng.bottom() + 1))
        return rows

    def updateSelectedRows(self) -> None:  # noqa: N802
        if self.selectionMode() == QTableView.SelectionMode.NoSelection:
            return
        delegate = self.delegate
        old = set(delegate.selectedRows)
        new = self._selected_row_set()
        delegate.selectedRows = new
        if delegate.pressedRow in new:
            delegate.pressedRow = -1
        self._update_rows(old ^ new)

    def resizeEvent(self, e) -> None:  # noqa: N802
        # Qt already repaints exposed areas on resize; Fluent's extra full update is redundant.
        QTableView.resizeEvent(self, e)


class RowIndex:
    """Maps a record id to the QTableWidgetItem that carries it, giving O(1) id -> row lookups.

    ``item.row()`` is maintained by Qt, so the lookup stays correct after sorting. Stale entries
    (row removed / table cleared) are detected and dropped.
    """

    def __init__(self) -> None:
        self._items: dict[Any, QTableWidgetItem] = {}

    def clear(self) -> None:
        self._items.clear()

    def add(self, key: Any, item: QTableWidgetItem) -> None:
        if key is not None:
            self._items[key] = item

    def row(self, table: QTableView, key: Any) -> int | None:
        item = self._items.get(key)
        if item is None:
            return None
        try:
            if item.tableWidget() is table:
                return item.row()
        except RuntimeError:  # underlying C++ item already deleted
            pass
        self._items.pop(key, None)
        return None
