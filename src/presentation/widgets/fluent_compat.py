"""
Compatibility patches for PyQt6-Fluent-Widgets on the installed Qt version.

SpinBox family (SpinBox, DoubleSpinBox, DateEdit, TimeEdit, DateTimeEdit and their Compact variants):
with Qt 6.12 + PyQt6-Fluent-Widgets 1.11.3, QAbstractSpinBox lays its inner QLineEdit out from a style
sub-control rect that collapses to 1 px (the widgets disable Qt's own buttons and draw Fluent ones),
so the value is invisible everywhere ("Nhảy dòng", schedule interval, batch upload interval...).
After every resize we place the line edit inside the area the Fluent stylesheet reserves for text
(padding 10px left; 80px right for inline buttons, 26px for compact ones).
"""

from __future__ import annotations

from typing import Any

_LEFT_PADDING = 10
_INLINE_RIGHT_PADDING = 80
_COMPACT_RIGHT_PADDING = 26
_NO_BUTTON_RIGHT_PADDING = 10

_applied = False


def _layout_line_edit(spin: Any) -> None:
    edit = spin.lineEdit()
    if edit is None:
        return
    if hasattr(spin, "compactSpinButton"):
        buttons_shown = not spin.compactSpinButton.isHidden()
        right = _COMPACT_RIGHT_PADDING if buttons_shown else _NO_BUTTON_RIGHT_PADDING
    else:
        up = getattr(spin, "upButton", None)
        buttons_shown = up is not None and not up.isHidden()
        right = _INLINE_RIGHT_PADDING if buttons_shown else _NO_BUTTON_RIGHT_PADDING
    width = max(10, spin.width() - _LEFT_PADDING - right)
    edit.setGeometry(_LEFT_PADDING, 0, width, spin.height())


def _needs_patch(spin_cls: type) -> bool:
    """True when Qt collapses the edit field (checked on a throw-away instance)."""
    probe = spin_cls()
    try:
        probe.resize(200, 33)
        probe.ensurePolished()
        from PyQt6.QtGui import QResizeEvent

        probe.resizeEvent(QResizeEvent(probe.size(), probe.size()))
        return probe.lineEdit().width() < 40
    finally:
        probe.deleteLater()


def apply_fluent_compat_patches() -> bool:
    """Installs the SpinBox geometry fix once (needs a QApplication). Returns True if patched."""
    global _applied
    if _applied:
        return True

    import qfluentwidgets as qfw
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return False

    names = (
        "SpinBox",
        "DoubleSpinBox",
        "DateEdit",
        "TimeEdit",
        "DateTimeEdit",
        "CompactSpinBox",
        "CompactDoubleSpinBox",
        "CompactDateEdit",
        "CompactTimeEdit",
        "CompactDateTimeEdit",
    )
    classes = [getattr(qfw, n) for n in names if hasattr(qfw, n)]
    if not classes or not _needs_patch(classes[0]):
        _applied = True  # library/Qt combination is fine: nothing to do
        return False

    for cls in classes:
        original = cls.resizeEvent

        def resizeEvent(self, e, _original=original):  # noqa: N802 - Qt API
            _original(self, e)
            _layout_line_edit(self)

        def showEvent(self, e, _original_show=cls.showEvent):  # noqa: N802 - Qt API
            _original_show(self, e)
            _layout_line_edit(self)

        cls.resizeEvent = resizeEvent
        cls.showEvent = showEvent
    _applied = True
    return True
