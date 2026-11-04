"""界面基件适配层：**主程序在旁边就用主程序的控件，不在就用兜底实现**。

页面代码只写一遍（用 ``Kit`` 的接口），于是：

* 主程序在旁边：``GlassCard`` / ``AppButton`` / ``ToastHost`` … 视觉与主程序完全一致；
* 主程序不在：兜底实现按同一套 ``theme`` 颜色画，仍然像个正经程序，不会崩。

这样将来把页面搬进主程序时，只需要删掉 ``Kit`` 这一层，控件名一一对应。
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..common import bridge


class _Card(QFrame):
    """兜底卡片：毛玻璃质感用半透明白 + 细边模拟。"""

    def __init__(self, parent=None, radius: int = 16, alpha: int = 150):
        super().__init__(parent)
        self._theme = bridge.theme()
        self.setObjectName("labCard")
        self.setStyleSheet(
            f"#labCard{{background:rgba(255,255,255,{max(0, min(255, alpha)) / 255:.3f});"
            f"border:1px solid rgba(34,52,86,36);border-radius:{radius}px;}}"
        )


class _Chip(QLabel):
    _COLORS = {"neutral": "sub", "blue": "blue", "green": "green", "red": "red",
               "amber": "amber", "purple": "purple", "teal": "teal"}

    def __init__(self, text: str = "", kind: str = "neutral", icon: str | None = None, parent=None):
        theme = bridge.theme()
        if icon:
            text = f"{theme.icon_char(icon)} {text}"
        super().__init__(text, parent)
        color = getattr(theme, "C_" + self._COLORS.get(kind, "sub").upper(), theme.C_SUB)
        self.setStyleSheet(
            f"QLabel{{color:{color};background:rgba(10,132,255,16);border-radius:8px;"
            f"padding:2px 8px;}}"
        )
        self.setFont(theme.font(11))


class _Button(QPushButton):
    _PALETTE = {
        "primary": ("#FFFFFF", "#0A84FF", "#0A76E0", "#0768C8"),
        "ghost": (None, "rgba(10,40,90,14)", "rgba(10,40,90,26)", "rgba(10,40,90,40)"),
        "soft": (None, "rgba(10,132,255,28)", "rgba(10,132,255,44)", "rgba(10,132,255,60)"),
        "danger": ("#FFFFFF", "#D70015", "#B80012", "#99000F"),
    }

    def __init__(self, label: str = "", icon: str | None = None, kind: str = "ghost",
                 size: str = "md", parent=None):
        theme = bridge.theme()
        text = f"{theme.icon_char(icon)}  {label}".strip() if icon else label
        super().__init__(text, parent)
        fg, bg, hover, press = self._PALETTE.get(kind, self._PALETTE["ghost"])
        fg = fg or theme.C_TEXT
        height = {"sm": 28, "md": 34, "lg": 38, "icon": 30}.get(size, 34)
        self.setFixedHeight(height)
        if size == "icon":
            self.setFixedWidth(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.font(11, theme.QFont.Weight.DemiBold if kind == "primary" else None))
        self.setStyleSheet(
            f"QPushButton{{color:{fg};background:{bg};border:none;border-radius:8px;"
            f"padding:0 12px;}}"
            f"QPushButton:hover{{background:{hover};}}"
            f"QPushButton:pressed{{background:{press};}}"
            f"QPushButton:disabled{{color:{theme.C_MUTED};background:rgba(120,120,130,20);}}"
        )


class _ToastHost(QWidget):
    """兜底提示条：贴在父窗口底部居中，几秒后自己消失。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._theme = bridge.theme()
        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._label.hide)
        self.hide()

    def show_message(self, text: str, kind: str = "ok", action_label: str | None = None,
                     on_action: Callable[[], None] | None = None, timeout: int = 2600):
        colors = {"ok": self._theme.C_GREEN, "warn": self._theme.C_AMBER,
                  "error": self._theme.C_RED, "info": self._theme.C_BLUE}
        fg = colors.get(kind, self._theme.C_TEXT)
        self._label.setText(text)
        self._label.setFont(self._theme.font(11.5))
        self._label.setStyleSheet(
            f"QLabel{{color:{fg};background:rgba(255,255,255,242);"
            f"border:1px solid rgba(34,52,86,48);border-radius:10px;padding:8px 16px;}}"
        )
        self._label.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            width = self._label.width()
            self._label.move(max(8, (parent.width() - width) // 2), max(8, parent.height() - 60))
        self._label.show()
        self._label.raise_()
        self._timer.start(max(800, int(timeout)))


class _SearchBoxWidget(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        theme = bridge.theme()
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(34)
        self.setFont(theme.font(12))
        self.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,220);border:1px solid rgba(34,52,86,40);"
            "border-radius:9px;padding:0 10px;}"
            f"QLineEdit:focus{{border:1px solid {theme.C_BLUE};}}"
        )


class _Segmented(QWidget):
    """兜底分段控件（选项卡）：两段以上按钮，选中项高亮。"""

    from PySide6.QtCore import Signal as _Signal

    changed = _Signal(str)

    def __init__(self, items, current=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton

        self.items = list(items)
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons = {}
        for key, label in self.items:
            btn = QPushButton(label, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _checked=False, k=key: self._pick(k))
            lay.addWidget(btn, 1)
            self.group.addButton(btn)
            self._buttons[key] = btn
        self._retint()
        self.set_current(current or self.items[0][0], emit=False)

    def _retint(self):
        theme = bridge.theme()
        dark = theme.MODE == "dark"
        base = "rgba(255,255,255,22)" if dark else "rgba(28,28,30,18)"
        on = "rgba(10,132,255,44)"
        for btn in self._buttons.values():
            btn.setStyleSheet(
                f"QPushButton{{color:{theme.C_SUB};background:{base};border:none;"
                f"border-radius:9px;font-size:11px;}}"
                f"QPushButton:checked{{color:{theme.C_BLUE};background:{on};font-weight:600;}}"
            )

    def _pick(self, key):
        self.changed.emit(key)

    def current(self):
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return self.items[0][0]

    def set_current(self, key, emit=False):
        btn = self._buttons.get(key)
        if not btn:
            return
        btn.setChecked(True)
        if emit:
            self.changed.emit(key)

    def sync_theme(self):
        self._retint()


class _NavButton(QPushButton):
    """兜底导航项：图标用图标字体渲染成 QIcon，文字用正文字体。"""

    def __init__(self, icon: str, label: str, parent=None):
        theme = bridge.theme()
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setFont(theme.font(12))
        self.setIconSize(QSize(18, 18))
        self.setIcon(_glyph_icon(theme, icon, 18, theme.C_SUB, theme.C_BLUE))
        self.setStyleSheet(
            f"QPushButton{{color:{theme.C_TEXT};background:transparent;border:none;"
            f"border-radius:10px;text-align:left;padding:0 14px;}}"
            f"QPushButton:hover{{background:rgba(10,132,255,16);}}"
            f"QPushButton:checked{{background:rgba(10,132,255,30);"
            f"color:{theme.C_BLUE};font-weight:600;}}"
        )


def _glyph_icon(theme, name: str, size: int, color: str, checked_color: str):
    """把图标字体的一个字画成 QIcon（普通态/选中态两套颜色）。"""
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

    icon = QIcon()
    for state, value in ((QIcon.State.Off, color), (QIcon.State.On, checked_color)):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(QColor(value))
        painter.setFont(theme.icon_font(size))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, theme.icon_char(name))
        painter.end()
        icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return icon


class Kit:
    """控件工厂。页面代码只依赖这里的名字。"""

    def __init__(self, theme=None, widgets=None):
        self.theme = theme if theme is not None else bridge.theme()
        self.widgets = widgets if widgets is not None else bridge.widgets()
        self.has_main_widgets = self.widgets is not None

    # ---------------------------------------------------------------- 卡片
    def card(self, parent=None, radius: int = 16, alpha: int = 150) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.GlassCard(parent, radius=radius, alpha=alpha)
        return _Card(parent, radius=radius, alpha=alpha)

    def card_layout(self, card: QWidget, *, margins=(16, 14, 16, 14), spacing: int = 10) -> QVBoxLayout:
        lay = QVBoxLayout(card)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        return lay

    # ---------------------------------------------------------------- 文字
    def title(self, text: str, size: float = 15) -> QLabel:
        label = QLabel(text)
        label.setFont(self.theme.font(size, self.theme.QFont.Weight.DemiBold))
        label.setStyleSheet(f"color:{self.theme.C_TEXT};background:transparent;")
        return label

    def text(self, text: str = "", size: float = 11.5, color: str | None = None,
             wrap: bool = False) -> QLabel:
        label = QLabel(text)
        label.setFont(self.theme.font(size))
        label.setStyleSheet(f"color:{color or self.theme.C_SUB};background:transparent;")
        if wrap:
            label.setWordWrap(True)
        return label

    def icon_label(self, name: str, size: int = 16, color: str | None = None,
                   parent=None) -> QLabel:
        if self.has_main_widgets:
            return self.widgets.IconLabel(name, size, color or self.theme.C_SUB, parent)
        label = QLabel(self.theme.icon_char(name), parent)
        label.setFont(self.theme.icon_font(size))
        label.setStyleSheet(f"color:{color or self.theme.C_SUB};background:transparent;")
        return label

    def chip(self, text: str = "", kind: str = "neutral", icon: str | None = None,
             parent=None) -> QLabel:
        if self.has_main_widgets:
            return self.widgets.Chip(text, kind, icon, parent)
        return _Chip(text, kind, icon, parent)

    def divider(self, parent=None) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.Divider(parent)
        line = QFrame(parent)
        line.setFixedHeight(1)
        line.setStyleSheet("background:rgba(34,52,86,28);")
        return line

    # ---------------------------------------------------------------- 交互
    def button(self, label: str = "", icon: str | None = None, kind: str = "ghost",
               size: str = "md", parent=None) -> QPushButton:
        if self.has_main_widgets:
            return self.widgets.AppButton(label, icon, kind, size, parent)
        return _Button(label, icon, kind, size, parent)

    def search_box(self, placeholder: str = "", parent=None) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.SearchBox(placeholder, parent)
        return _SearchBoxWidget(placeholder, parent)

    def toast_host(self, parent) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.ToastHost(parent)
        return _ToastHost(parent)

    def nav_button(self, icon: str, label: str, parent=None):
        """侧栏导航项（主程序在旁边就用主程序的 NavButton，视觉完全一致）。"""
        if self.has_main_widgets:
            return self.widgets.NavButton(icon, label, parent)
        return _NavButton(icon, label, parent)

    def select(self, parent=None) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.Select(parent)
        from PySide6.QtWidgets import QComboBox

        return QComboBox(parent)

    def segmented(self, items, current: str | None = None, parent=None):
        """分段控件（选项卡）。主程序在旁边就用它的 Segmented，视觉一致。"""
        if self.has_main_widgets:
            return self.widgets.Segmented(items, current, parent)
        return _Segmented(items, current, parent)

    def empty_state(self, icon: str, title: str, desc: str, parent=None) -> QWidget:
        if self.has_main_widgets:
            return self.widgets.EmptyState(icon, title, desc, None, parent)
        box = QWidget(parent)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 24, 0, 24)
        lay.setSpacing(6)
        head = self.icon_label(icon, 30, self.theme.C_MUTED)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)
        name = self.text(title, 13, self.theme.C_SUB)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)
        detail = self.text(desc, 11, self.theme.C_MUTED, wrap=True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(detail)
        lay.addStretch(1)
        return box

    def confirm(self, parent, title: str, text: str, ok_label: str = "确定") -> bool:
        """二次确认。有主程序就用它的 ``ask_confirm``，保证弹窗长得一样。"""
        if self.has_main_widgets and hasattr(self.widgets, "ask_confirm"):
            try:
                return bool(self.widgets.ask_confirm(parent, title, text, ok_label))
            except Exception:  # noqa: BLE001 - 主程序签名变化时退回系统弹窗
                pass
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        ok = box.addButton(ok_label, QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is ok

    # ---------------------------------------------------------------- 布局
    @staticmethod
    def row(*items: Any, spacing: int = 8, stretch_at_end: bool = True,
            margins=(0, 0, 0, 0)) -> QWidget:
        """把若干控件横着排。传 ``None`` 表示插入一个弹性空隙。"""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        for item in items:
            if item is None:
                lay.addStretch(1)
            elif isinstance(item, QWidget):
                lay.addWidget(item)
            else:
                lay.addLayout(item)
        if stretch_at_end and (not items or items[-1] is not None):
            lay.addStretch(1)
        return box
