"""
Standardized UI helper utilities for Windows 11 Fluent Design dialogs.
Provides consistent header banners, typography, margins, and button layout patterns.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, isDarkTheme

# Industrial standard geometry for all application dialogs
STANDARD_DIALOG_MARGINS = (20, 18, 20, 18)
STANDARD_DIALOG_SPACING = 12


def create_dialog_header(
    icon: FluentIcon,
    title: str,
    subtitle: str = "",
    parent: QWidget | None = None,
) -> QWidget:
    """
    Creates a standardized Windows 11 Fluent Design dialog header banner.
    Includes a sharp vector SVG icon, bold title, and subtle descriptive subtitle.
    """
    header_container = QWidget(parent)
    header_layout = QHBoxLayout(header_container)
    header_layout.setContentsMargins(0, 0, 0, 4)
    header_layout.setSpacing(12)

    # 1. High-DPI Vector Icon Widget
    icon_widget = IconWidget(icon, header_container)
    icon_widget.setFixedSize(28, 28)
    header_layout.addWidget(icon_widget, 0, Qt.AlignmentFlag.AlignTop)

    # 2. Title & Subtitle vertical stack
    text_container = QWidget(header_container)
    text_layout = QVBoxLayout(text_container)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(2)

    title_color = "#F3F4F6" if isDarkTheme() else "#1F2937"
    sub_color = "#9CA3AF" if isDarkTheme() else "#6B7280"

    title_label = QLabel(title, text_container)
    title_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {title_color};")
    text_layout.addWidget(title_label)

    if subtitle:
        subtitle_label = QLabel(subtitle, text_container)
        subtitle_label.setStyleSheet(f"font-size: 12px; color: {sub_color};")
        subtitle_label.setWordWrap(True)
        text_layout.addWidget(subtitle_label)

    header_layout.addWidget(text_container, 1)

    return header_container


def apply_dialog_standard_layout(layout: QLayout) -> None:
    """Applies standardized contents margins and widget spacing to any dialog layout."""
    layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
    layout.setSpacing(STANDARD_DIALOG_SPACING)
