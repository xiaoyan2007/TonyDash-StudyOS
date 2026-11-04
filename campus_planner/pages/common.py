"""页面共用的小部件。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme, widgets


class PageHeader(QWidget):
    """页头：eyebrow + 标题 + 动态副标题 + 固定的使用提示。"""

    def __init__(self, eyebrow: str, title: str, subtitle: str = "", parent=None,
                 hint: str = ""):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.eyebrow = QLabel(eyebrow.capitalize() if eyebrow.isascii() else eyebrow, self)
        self.eyebrow.setFont(theme.font(11, theme.QFont.Weight.DemiBold))
        self.eyebrow.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        lay.addWidget(self.eyebrow)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.title = QLabel(title, self)
        self.title.setFont(theme.font(26, theme.QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        row.addWidget(self.title)
        row.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        row.addLayout(self.actions)
        lay.addLayout(row)
        self.subtitle = QLabel(subtitle, self)
        self.subtitle.setFont(theme.font(12))
        self.subtitle.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)

        # 固定的“这一页怎么用”，不会被动态副标题覆盖
        self.hint_row = QWidget(self)
        self.hint_row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self.hint_row)
        hl.setContentsMargins(0, 2, 0, 0)
        hl.setSpacing(6)
        hl.addWidget(widgets.IconLabel("info", 12, theme.C_BLUE))
        self.hint = QLabel(hint, self.hint_row)
        self.hint.setFont(theme.font(11))
        self.hint.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        self.hint.setWordWrap(True)
        hl.addWidget(self.hint, 1)
        lay.addWidget(self.hint_row)
        self.hint_row.setVisible(bool(hint))

    def add_action(self, widget: QWidget):
        self.actions.addWidget(widget)

    def set_eyebrow(self, text: str):
        self.eyebrow.setText(text)

    def set_subtitle(self, text: str):
        self.subtitle.setText(text)

    def set_hint(self, text: str):
        self.hint.setText(text)
        self.hint_row.setVisible(bool(text))


def icon_text(name: str, text: str, color: str = None, size: float = 11) -> QLabel:
    color = color or theme.C_SUB
    lab = QLabel()
    lab.setFont(theme.font(size))
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setText(
        f"<span style='font-family:\"{theme.icon_family()}\"; color:{color};'>"
        f"{theme.icon_char(name)}</span>"
        f"<span style='color:{color};'>&nbsp;{text}</span>"
    )
    lab.setStyleSheet("background: transparent;")
    return lab


def vspace(height: int) -> QWidget:
    w = QWidget()
    w.setFixedHeight(height)
    w.setStyleSheet("background: transparent;")
    return w


def card(radius: int = 16, alpha: int = 120) -> widgets.GlassCard:
    c = widgets.GlassCard(radius=radius, alpha=alpha)
    return c


def field_row(caption: str, widget: QWidget) -> QWidget:
    """小标题 + 控件的竖排小组件。"""
    box = QWidget()
    box.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    cap = QLabel(caption)
    cap.setFont(theme.font(11))
    cap.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
    lay.addWidget(cap)
    lay.addWidget(widget)
    return box
