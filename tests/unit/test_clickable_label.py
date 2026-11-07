"""The video-panel header is a real clickable label (no monkeypatched mousePressEvent: mypy rejects it)."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent


def _press(button: Qt.MouseButton) -> QMouseEvent:
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(5.0, 5.0), button, button, Qt.KeyboardModifier.NoModifier
    )


def test_left_click_emits_clicked_other_buttons_do_not(qtbot):
    from src.presentation.widgets.clickable_label import ClickableLabel

    lbl = ClickableLabel("x")
    qtbot.addWidget(lbl)
    hits: list[bool] = []
    lbl.clicked.connect(lambda: hits.append(True))
    lbl.mousePressEvent(_press(Qt.MouseButton.RightButton))
    assert hits == []
    lbl.mousePressEvent(_press(Qt.MouseButton.LeftButton))
    assert hits == [True]
    assert lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_main_window_header_is_a_clickable_label():
    import inspect

    from src.presentation.views import main_window

    src = inspect.getsource(main_window)
    assert "mousePressEvent =" not in src
    assert "ClickableLabel(" in src
