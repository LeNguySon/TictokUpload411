"""
Standardized UI helper utilities for Windows 11 Fluent Design dialogs.
Provides consistent header banners, typography, margins, group boxes, tabs, tables and cards.

Rules (instinct 030 / UI audit):
- Fluent widgets only (CheckBox, PushButton, SpinBox, DateTimeEdit...), never raw Qt ones.
- No emoji as icons: use FluentIcon.
- A literal "&" in a button / checkbox / group-box / tab text must be written "&&" (mnemonic).
- Never call setStyleSheet() with bare properties on a container: it cascades to every child
  (all QLabels got borders). Use the scoped helpers below.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, isDarkTheme, themeColor

from src.presentation.widgets.fluent_compat import apply_fluent_compat_patches

# Industrial standard geometry for all application dialogs
STANDARD_DIALOG_MARGINS = (20, 18, 20, 18)
STANDARD_DIALOG_SPACING = 12

# Semantic status colors shared by dialogs (light theme first, dark theme second).
STATUS_COLORS = {
    "success": ("#0F7B0F", "#6CCB5F"),
    "warning": ("#9D5D00", "#FCE100"),
    "danger": ("#C42B1C", "#FF99A4"),
    "info": ("#005FB8", "#60CDFF"),
    "neutral": ("#5C5C5C", "#C5C5C5"),
}
STATUS_BACKGROUNDS = {
    "success": ("#DFF6DD", "#393D1B"),
    "warning": ("#FFF4CE", "#433519"),
    "danger": ("#FDE7E9", "#442726"),
    "info": ("#E5F1FB", "#1F3546"),
    "neutral": ("#F3F3F3", "#2B2B2B"),
}


def status_color(kind: str) -> str:
    light, dark = STATUS_COLORS.get(kind, STATUS_COLORS["neutral"])
    return dark if isDarkTheme() else light


def status_background(kind: str) -> str:
    light, dark = STATUS_BACKGROUNDS.get(kind, STATUS_BACKGROUNDS["neutral"])
    return dark if isDarkTheme() else light


def create_dialog_header(
    icon: FluentIcon,
    title: str,
    subtitle: str = "",
    parent: QWidget | None = None,
) -> QWidget:
    """
    Creates a standardized Windows 11 Fluent Design dialog header banner.
    Includes a sharp vector SVG icon, bold title, and subtle descriptive subtitle.
    The banner never grows vertically (extra dialog height must not pull title and subtitle apart).
    """
    apply_fluent_compat_patches()

    header_container = QWidget(parent)
    header_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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


def style_group_box(group: QGroupBox) -> QGroupBox:
    """Fluent-like section: rounded subtle border, semibold title (replaces the native square frame)."""
    border = "rgba(255, 255, 255, 0.10)" if isDarkTheme() else "rgba(0, 0, 0, 0.08)"
    bg = "rgba(255, 255, 255, 0.04)" if isDarkTheme() else "rgba(255, 255, 255, 0.55)"
    title = "#E5E7EB" if isDarkTheme() else "#1F2937"
    group.setStyleSheet(
        f"""
        QGroupBox {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
            margin-top: 18px;
            padding: 6px 8px 8px 8px;
            font-weight: 600;
            font-size: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 4px;
            padding: 0 2px 4px 2px;
            color: {title};
        }}
        """
    )
    return group


def style_tab_widget(tabs: QTabWidget) -> QTabWidget:
    """Flat Fluent-like tabs with an accent underline (replaces the Windows-classic tab look)."""
    accent = themeColor().name()
    text = "#C5C5C5" if isDarkTheme() else "#5C5C5C"
    active = "#FFFFFF" if isDarkTheme() else "#1F2937"
    border = "rgba(255, 255, 255, 0.10)" if isDarkTheme() else "rgba(0, 0, 0, 0.08)"
    pane_bg = "rgba(255, 255, 255, 0.04)" if isDarkTheme() else "rgba(255, 255, 255, 0.55)"
    tabs.setDocumentMode(False)
    tabs.setStyleSheet(
        f"""
        QTabWidget::pane {{
            border: 1px solid {border};
            border-radius: 8px;
            background-color: {pane_bg};
            top: -1px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {text};
            padding: 7px 14px;
            margin-right: 2px;
            border: none;
            border-bottom: 2px solid transparent;
            font-size: 12px;
        }}
        QTabBar::tab:hover {{ color: {active}; }}
        QTabBar::tab:selected {{
            color: {active};
            font-weight: 600;
            border-bottom: 2px solid {accent};
        }}
        """
    )
    return tabs


def style_plain_table(table: QTableWidget) -> QTableWidget:
    """Brings a plain QTableWidget visually in line with the Fluent tables of the main window."""
    border = "rgba(255, 255, 255, 0.10)" if isDarkTheme() else "rgba(0, 0, 0, 0.08)"
    header_bg = "#2B2B2B" if isDarkTheme() else "#F7F7F7"
    header_fg = "#C5C5C5" if isDarkTheme() else "#5C5C5C"
    base = "#202020" if isDarkTheme() else "#FFFFFF"
    alt = "#262626" if isDarkTheme() else "#FAFAFA"
    sel = themeColor().name()
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setStyleSheet(
        f"""
        QTableWidget {{
            border: 1px solid {border};
            border-radius: 8px;
            background-color: {base};
            alternate-background-color: {alt};
            selection-background-color: rgba(0, 0, 0, 0.06);
            selection-color: palette(text);
        }}
        QTableWidget::item {{ padding: 0px 6px; border: none; }}
        QTableWidget::item:selected {{ border-left: 2px solid {sel}; }}
        QHeaderView::section {{
            background-color: {header_bg};
            color: {header_fg};
            border: none;
            border-bottom: 1px solid {border};
            padding: 4px 6px;
            font-size: 12px;
        }}
        """
    )
    return table


def style_card(frame: QFrame, kind: str = "neutral", object_name: str = "card") -> QFrame:
    """Rounded card styled through an objectName selector so the style does NOT cascade to child labels."""
    frame.setObjectName(object_name)
    border = "rgba(255, 255, 255, 0.10)" if isDarkTheme() else "rgba(0, 0, 0, 0.08)"
    bg = status_background(kind) if kind != "neutral" else ("#2B2B2B" if isDarkTheme() else "#FFFFFF")
    frame.setStyleSheet(
        f"QFrame#{object_name} {{ background-color: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
    )
    return frame


def fit_dialog_to_content(dialog: QWidget) -> None:
    """Sizes a dialog to its content height (keeping its width), instead of a fixed height that left
    large empty areas or stretched sections."""
    layout = dialog.layout()
    if layout is not None:
        layout.activate()
    dialog.resize(max(dialog.width(), dialog.minimumSizeHint().width()), dialog.sizeHint().height())
