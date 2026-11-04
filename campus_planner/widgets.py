"""通用界面组件：玻璃卡片、按钮、标签、开关、分段控件、提示条、弹窗。"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, Property, QRect, QRectF, QSize,
    Qt, QTimer, Signal, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPalette, QPen,
    QPolygonF, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QDateEdit, QDialog, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QCalendarWidget, QLineEdit, QListWidget, QMenu, QPushButton, QSizePolicy, QSlider,
    QTimeEdit,
    QVBoxLayout, QWidget,
)

from . import theme


# ---------------------------------------------------------------- 基础
class GlassCard(QFrame):
    """半透明白色圆角卡片。"""

    def __init__(self, parent=None, radius: int = 16, alpha: int = 150,
                 border_alpha: int = 225):
        super().__init__(parent)
        self.radius = radius
        self.alpha = alpha
        self.border_alpha = border_alpha
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def paintEvent(self, event):
        p = QPainter(self)
        theme.paint_glass(p, QRectF(self.rect()), self.radius, self.alpha, self.border_alpha)
        p.end()


class IconLabel(QLabel):
    def __init__(self, name: str, size: int = 16, color: str = None, parent=None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color = color or theme.C_SUB
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(size + 4, size + 4)
        self._draw()

    def _draw(self):
        if self._name in theme.VECTOR_ICONS:
            self.setPixmap(theme.vector_icon_pixmap(self._name, self._size, self._color))
        else:
            self.setFont(theme.icon_font(self._size))
            self.setText(theme.icon_char(self._name))

    def set_icon(self, name: str):
        self._name = name
        self._draw()

    def set_color(self, color: str):
        self._color = color
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self._draw()


class AppButton(QPushButton):
    """自绘按钮：primary / ghost / soft / danger / white。"""

    def __init__(self, label: str = "", icon: str | None = None, kind: str = "ghost",
                 size: str = "md", parent=None):
        super().__init__(parent)
        self.label = label
        self.icon_name = icon
        self.kind = kind
        self.size_name = size
        self._hover = False
        self._down = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFont(theme.font(11 if size == "sm" else 12))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # -- 尺寸
    def _height(self) -> int:
        return {"sm": 30, "md": 36, "lg": 40, "icon": 30}.get(self.size_name, 36)

    def _icon_px(self) -> int:
        base = {"sm": 13, "md": 15, "lg": 16, "icon": 18}.get(self.size_name, 15)
        # emoji 字形自带边距且比字号更宽，放大一档才看得清楚
        if self.icon_name in theme.EMOJIS:
            return int(base * 1.5)
        return base

    def sizeHint(self) -> QSize:
        h = self._height()
        if self.size_name == "icon" or (self.icon_name and not self.label):
            return QSize(h, h)
        fm = QFontMetrics(theme.font(11 if self.size_name == "sm" else 12, theme.QFont.Weight.DemiBold if self.kind == "primary" else theme.QFont.Weight.Normal))
        tw = fm.horizontalAdvance(self.label) if self.label else 0
        iw = (self._icon_px() + (5 if self.label else 0)) if self.icon_name else 0
        pad = 14 if self.size_name == "sm" else 17
        return QSize(max(h, tw + iw + pad * 2), h)

    # -- 事件
    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._down = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._down = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._down = False
        self.update()
        super().mouseReleaseEvent(event)

    # -- 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        h = self.height()
        radius = 9 if h <= 32 else (12 if h >= 40 else 10)
        enabled = self.isEnabled()
        checked = self.isChecked()

        if self.kind == "primary":
            bg = QColor(theme.C_BLUE)
            if self._down:
                bg = QColor(theme.C_BLUE_PRESS)
            elif self._hover:
                bg = QColor(theme.C_BLUE_HOVER)
            if not enabled:
                bg.setAlpha(95)
            fg = QColor("#FFFFFF")
        elif self.kind == "soft":
            a = 52 if self._down else (44 if self._hover else 32)
            bg = QColor(10, 132, 255, a)
            fg = QColor(theme.C_BLUE)
        elif self.kind == "danger":
            a = 58 if self._down else (48 if self._hover else 32)
            bg = QColor(255, 59, 48, a)
            fg = QColor(theme.C_RED)
        elif self.kind == "white":
            bg = QColor(255, 255, 255, 252 if self._hover else 238)
            # 白底按钮在深色模式下也必须用深色文字，否则浅色文字看不见
            fg = QColor("#1B1B1F")
        else:
            if checked:
                bg = QColor(10, 132, 255, 46 if self._hover else 32)
                fg = QColor(theme.C_BLUE)
            else:
                bg = QColor(28, 28, 30, 22 if self._down else (14 if self._hover else 0))
                fg = QColor(theme.C_TEXT)
        if not enabled:
            fg.setAlpha(110)

        # 浅色按钮先铺落影，避免与浅背景完全融合
        if self.kind in ("white", "ghost") and enabled:
            shadow = QPainterPath()
            shadow.addRoundedRect(rect.adjusted(0.5, 2.5, -0.5, 1.5), radius, radius)
            p.fillPath(shadow, QColor(32, 56, 102, 26 if self._hover else 16))

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if bg.alpha() > 0:
            p.fillPath(path, bg)
        if self.kind == "white":
            p.setPen(QPen(QColor(28, 28, 30, 30), 1))
            p.drawPath(path)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            p.drawLine(QPointF(rect.left() + radius, rect.top() + 1.2),
                       QPointF(rect.right() - radius, rect.top() + 1.2))
        elif self.kind == "ghost" and not self.label:
            p.setPen(QPen(QColor(28, 28, 30, 16), 1))
            p.drawPath(path)

        if self.hasFocus() and enabled:
            # 焦点环画在内部；画在外侧会被裁掉，只剩四个蓝角
            ring = QPainterPath()
            ring.addRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), radius - 1.5, radius - 1.5)
            p.setPen(QPen(QColor(10, 132, 255, 130), 2))
            p.drawPath(ring)

        # 内容
        p.setPen(fg)
        fm = QFontMetrics(self.font())
        tw = fm.horizontalAdvance(self.label) if self.label else 0
        icon_px = self._icon_px()
        gap = 6 if self.label else 0
        total = (icon_px if self.icon_name else 0) + (gap if self.icon_name and self.label else 0) + tw
        x = (self.width() - total) / 2.0
        if self.icon_name:
            if self.icon_name in theme.EMOJIS:
                p.setFont(theme.emoji_font(icon_px))
                if self.label:
                    p.drawText(QRectF(x, 0, icon_px + 10, h),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                               theme.emoji_char(self.icon_name))
                else:
                    # emoji 字形比字号宽，用全宽居中，避免被矩形裁切
                    p.drawText(QRectF(0, 0, self.width(), h),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter,
                               theme.emoji_char(self.icon_name))
            elif self.icon_name in theme.VECTOR_ICONS:
                pm = theme.vector_icon_pixmap(self.icon_name, icon_px, fg)
                p.drawPixmap(QPointF(x, (h - icon_px) / 2.0), pm)
            else:
                p.setFont(theme.icon_font(icon_px))
                p.drawText(QRectF(x, 0, icon_px, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           theme.icon_char(self.icon_name))
            x += icon_px + gap
        if self.label:
            if self.kind == "primary":
                p.setFont(theme.font(11 if self.size_name == "sm" else 12, theme.QFont.Weight.DemiBold))
            else:
                p.setFont(theme.font(11 if self.size_name == "sm" else 12))
            p.drawText(QRectF(x, 0, tw + 2, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self.label)
        p.end()


class NavButton(QAbstractButton):
    """左侧导航项，带图标、文字和计数。"""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.label = label
        self.count = 0
        self._hover = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_count(self, count: int):
        if count != self.count:
            self.count = int(count)
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        radius = 11.0
        checked = self.isChecked()
        if checked:
            bg = QColor(theme.C_BLUE)
        elif self._hover:
            bg = QColor(10, 132, 255, 24)
        else:
            bg = QColor(0, 0, 0, 0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if bg.alpha():
            p.fillPath(path, bg)
        fg = QColor("#FFFFFF" if checked else theme.C_TEXT)
        p.setPen(fg)
        p.setFont(theme.icon_font(18))
        p.drawText(QRectF(14, 0, 22, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, theme.icon_char(self.icon_name))
        p.setFont(theme.font(12, theme.QFont.Weight.DemiBold if checked else theme.QFont.Weight.Normal))
        p.drawText(QRectF(44, 0, self.width() - 86, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)
        if self.count:
            text = str(self.count)
            fm = QFontMetrics(theme.font(11.5, theme.QFont.Weight.DemiBold))
            w = max(20, fm.horizontalAdvance(text) + 12)
            pill = QRectF(self.width() - w - 12, (self.height() - 19) / 2, w, 19)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 230) if checked else QColor(28, 28, 30, 24))
            p.drawRoundedRect(pill, 9.5, 9.5)
            p.setPen(QColor(theme.C_BLUE) if checked else QColor(theme.C_SUB))
            p.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        if self.hasFocus():
            ring = QPainterPath()
            ring.addRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), radius - 1.5, radius - 1.5)
            p.setPen(QPen(QColor(10, 132, 255, 130), 2))
            p.drawPath(ring)
        p.end()


class Chip(QLabel):
    def _palette(self):
        """按当前主题返回 {kind: (底色, 文字色)}。

        深色模式下文字色取主题高亮色（蓝/绿/红/琥珀），否则深色文字
        落在深色玻璃上会看不见。
        """
        t = theme.tokens()
        dark = theme.MODE == "dark"
        card = t["card"]
        return {
            "neutral": (theme.rgba_str(card, 24 if dark else 22), t["sub"]),
            "accent": (theme.rgba_str((10, 132, 255), 46 if dark else 42), t["blue"]),
            "green": (theme.rgba_str((52, 199, 89), 40 if dark else 36), t["green"]),
            "red": (theme.rgba_str((255, 59, 48), 38 if dark else 32), t["red"]),
            "amber": (theme.rgba_str((255, 159, 10), 44 if dark else 38), t["amber"]),
            "white": (theme.rgba_str((255, 255, 255), 200), "#1C1C1E"),
        }

    def __init__(self, text: str = "", kind: str = "neutral", icon: str | None = None,
                 parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self.icon_name = icon
        self._hover = False
        self.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def apply_theme(self):
        # 颜色在 paintEvent 里按 theme.MODE 现算，重绘即可。
        self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text())
        if self.icon_name:
            w += 15
        return QSize(w + 16, 22)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self._palette()
        bg, fg = pal.get(self.kind, pal["neutral"])
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)
        p.fillPath(path, QColor(bg) if not bg.startswith("rgba") else _rgba(bg))
        p.setPen(QColor(fg))
        fm = QFontMetrics(self.font())
        tw = fm.horizontalAdvance(self.text())
        total = tw + (15 if self.icon_name else 0)
        x = (self.width() - total) / 2
        if self.icon_name:
            p.setFont(theme.icon_font(10))
            p.drawText(QRectF(x, 0, 14, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       theme.icon_char(self.icon_name))
            x += 15
        p.setFont(self.font())
        p.drawText(QRectF(x, 0, tw + 2, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        p.end()


def _rgba(text: str) -> QColor:
    """解析 'rgba(r, g, b, a)'。"""
    inner = text[text.index("(") + 1:text.rindex(")")]
    parts = [int(float(x.strip())) for x in inner.split(",")]
    if len(parts) == 4:
        return QColor(parts[0], parts[1], parts[2], parts[3])
    return QColor(parts[0], parts[1], parts[2])


class Switch(QAbstractButton):
    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _on_anim(self, value):
        self._pos = float(value)
        self.update()

    def _animate(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, 4, 40, 16)
        off = QColor(120, 120, 128, 85)
        on = QColor(theme.C_BLUE)
        col = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
            int(off.alpha() + (on.alpha() - off.alpha()) * self._pos),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, 8, 8)
        x = 3 + self._pos * 20
        p.setBrush(QColor(0, 0, 0, 28))
        p.drawEllipse(QRectF(x, 5.5, 18, 18))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(x, 4, 18, 18))
        p.end()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            return
        super().keyPressEvent(event)


class SegmentButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFont(theme.font(11))
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.isChecked():
            path = QPainterPath()
            path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
            p.fillPath(path, QColor(theme.C_BLUE))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(theme.font(11, theme.QFont.Weight.DemiBold))
        else:
            if self._hover:
                path = QPainterPath()
                path.addRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
                p.fillPath(path, QColor(255, 255, 255, 30) if theme.MODE == "dark"
                           else QColor(255, 255, 255, 160))
            p.setPen(QColor(theme.C_SUB))
            p.setFont(theme.font(11))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, items, current: str | None = None, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.setFixedHeight(38)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, SegmentButton] = {}
        for key, label in self.items:
            btn = SegmentButton(label, self)
            btn.setProperty("key", key)
            lay.addWidget(btn, 1)
            self.group.addButton(btn)
            self.buttons[key] = btn
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
        self.set_current(current or self.items[0][0], emit=False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 34) if theme.MODE == "dark"
                   else QColor(28, 28, 30, 26))
        p.drawRoundedRect(QRectF(self.rect()), 9, 9)
        p.end()

    def _pick(self, key: str):
        self.changed.emit(key)

    def current(self) -> str:
        for key, btn in self.buttons.items():
            if btn.isChecked():
                return key
        return self.items[0][0]

    def set_current(self, key: str, emit: bool = False):
        btn = self.buttons.get(key)
        if not btn:
            return
        btn.setChecked(True)
        if emit:
            self.changed.emit(key)


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(False)
        self.setMinimumHeight(38)
        self._icon = QLabel(self)
        self._icon.setFont(theme.icon_font(14))
        self._icon.setText(theme.icon_char("search"))
        self._icon.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self._icon.setFixedSize(18, 18)
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._clear = AppButton("", "close", "ghost", "icon")
        self._clear.setFixedSize(22, 22)
        self._clear.setToolTip("清空搜索")
        self._clear.hide()
        self._clear.clicked.connect(self.clear)
        self.textChanged.connect(lambda t: self._clear.setVisible(bool(t)))
        self.setStyleSheet("QLineEdit { padding-left: 30px; padding-right: 30px; }")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        self._icon.move(11, (h - 18) // 2)
        self._clear.move(self.width() - 27, (h - 22) // 2)


class ProgressBar(QWidget):
    def __init__(self, value: int = 0, parent=None, color: str = None,
                 height: int = 6):
        super().__init__(parent)
        self._value = max(0, min(100, int(value)))
        self._color = QColor(color or theme.C_BLUE)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int):
        value = max(0, min(100, int(value)))
        if value != self._value:
            self._value = value
            self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.setPen(Qt.PenStyle.NoPen)
        bg = (255, 255, 255, 34) if theme.MODE == "dark" else (28, 28, 30, 18)
        p.setBrush(QColor(*bg))
        p.drawRoundedRect(QRectF(0, 0, r.width(), r.height()), r.height() / 2, r.height() / 2)
        if self._value > 0:
            p.setBrush(self._color)
            p.drawRoundedRect(QRectF(0, 0, max(r.height(), r.width() * self._value / 100.0), r.height()),
                              r.height() / 2, r.height() / 2)
        p.end()


class SmoothSlider(QSlider):
    """自绘滑块：带缓动跟随，拖动与点击都更顺滑。"""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMinimumHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._hover = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.setMouseTracking(True)
        self.valueChanged.connect(self._sync_pos)

    def _on_anim(self, value):
        self._pos = float(value)
        self.update()

    def sync_value(self):
        self._sync_pos(self.value())

    def _sync_pos(self, value):
        lo, hi = self.minimum(), self.maximum()
        ratio = (value - lo) / (hi - lo) if hi > lo else 0.0
        if abs(self._pos - ratio) > 0.001:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(ratio)
            self._anim.start()

    def showEvent(self, event):
        super().showEvent(event)
        lo, hi = self.minimum(), self.maximum()
        self._pos = (self.value() - lo) / (hi - lo) if hi > lo else 0.0

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = 6.0
        y = (self.height() - h) / 2
        w = self.width() - 2
        track = QRectF(1, y, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*theme.tokens()["card_border"][:3], 46)
                   if theme.MODE == "light" else QColor(255, 255, 255, 46))
        p.drawRoundedRect(track, h / 2, h / 2)
        fill_w = max(h, w * self._pos)
        p.setBrush(QColor(theme.C_BLUE))
        p.drawRoundedRect(QRectF(1, y, fill_w, h), h / 2, h / 2)
        knob_r = 10.0 if self._hover or self.isSliderDown() else 9.0
        cx = 1 + fill_w
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(theme.C_BLUE), 2))
        p.drawEllipse(QPointF(cx, y + h / 2), knob_r, knob_r)
        p.end()


class SplitProgressBar(QWidget):
    """全宽双色进度条：已完成绿色、未完成红色，切换时带缓动动画。"""

    def __init__(self, parent=None, height: int = 7):
        super().__init__(parent)
        self._progress = 0.0
        self._total = 0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(480)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    progress = Property(float, progress, _set_progress)

    def ratio(self) -> float:
        return self._progress

    def set_ratio(self, done: int, total: int, animate: bool = True):
        self._total = total
        target = (done / total) if total else 0.0
        target = max(0.0, min(1.0, target))
        self._anim.stop()
        if animate and self.isVisible() and abs(target - self._progress) > 0.001:
            self._anim.setStartValue(self._progress)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_progress(target)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        radius = h / 2
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40) if theme.MODE == "dark"
                   else QColor(28, 28, 30, 26))
        p.drawRect(QRectF(0, 0, w, h))
        if self._total <= 0:
            p.end()
            return
        gw = w * self._progress
        if gw > 0:
            p.setBrush(QColor(theme.C_GREEN))
            p.drawRect(QRectF(0, 0, gw, h))
        if w - gw > 0:
            p.setBrush(QColor(theme.C_RED))
            p.drawRect(QRectF(gw, 0, w - gw, h))
        p.end()


class StatTile(GlassCard):
    def __init__(self, caption: str, value: str = "0", unit: str = "", parent=None,
                 color: str = None):
        super().__init__(parent, radius=14, alpha=182)
        self._caption = caption
        self._value = value
        self._unit = unit
        self._color = color or theme.C_TEXT
        self.setMinimumHeight(100)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(3)
        self.value_label = QLabel(self)
        self.caption_label = QLabel(caption, self)
        self.caption_label.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
        self.caption_label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        lay.addWidget(self.value_label)
        lay.addWidget(self.caption_label)
        lay.addStretch(1)
        self._render()

    def _render(self):
        color = self._color
        self.value_label.setText(
            f'<span style="font-size:27px; font-weight:700; color:{color};">{self._value}</span>'
            + (f'<span style="font-size:12px; color:{theme.C_SUB};"> {self._unit}</span>' if self._unit else "")
        )
        self.value_label.setTextFormat(Qt.TextFormat.RichText)

    def set_value(self, value: str, color: str | None = None):
        self._value = value
        if color:
            self._color = color
        self._render()


class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, desc: str, action: QWidget | None = None,
                 parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(0)
        lay.addStretch(2)
        badge = IconBadge(icon, 72, parent=self)
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        t = QLabel(title, self)
        t.setFont(theme.font(19, theme.QFont.Weight.DemiBold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("background: transparent;")
        lay.addWidget(t)
        if desc:
            lay.addSpacing(8)
            d = QLabel(desc, self)
            d.setFont(theme.font(12.5))
            d.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            d.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d.setWordWrap(True)
            d.setMaximumWidth(440)
            # 高度按「实际换行后的行数」算，不能写死 2 行：说明文字里带空行、
            # 换行后常占 3~4 行，写死高度会被父布局压扁、后半句被裁掉看不见。
            fm = d.fontMetrics()
            width = 440
            flags = int(Qt.TextFlag.TextWordWrap)
            rect = fm.boundingRect(0, 0, width, 10_000, flags, desc)
            d.setMinimumHeight(rect.height() + 6)
            d.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            lay.addWidget(d, 0, Qt.AlignmentFlag.AlignHCenter)
        if action is not None:
            lay.addSpacing(20)
            lay.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(3)


class IconBadge(QWidget):
    def __init__(self, icon: str, size: int = 56, parent=None,
                 bg: QColor | None = None, fg: QColor | None = None):
        super().__init__(parent)
        self.icon_name = icon
        self._size = size
        self._bg = bg or QColor(10, 132, 255, 28)
        self._fg = fg or QColor(theme.C_BLUE)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bg)
        p.drawEllipse(QRectF(0, 0, self._size, self._size))
        p.setPen(self._fg)
        p.setFont(theme.icon_font(int(self._size * 0.46)))
        p.drawText(QRectF(0, 0, self._size, self._size), Qt.AlignmentFlag.AlignCenter,
                   theme.icon_char(self.icon_name))
        p.end()


class ColorSwatches(QWidget):
    changed = Signal(int)

    def __init__(self, current: int = 1, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: list[SwatchButton] = []
        for i in range(1, 9):
            b = SwatchButton(i, self)
            lay.addWidget(b)
            self.group.addButton(b)
            self._buttons.append(b)
            b.clicked.connect(lambda _=False, idx=i: self.changed.emit(idx))
        self.set_current(current)

    def current(self) -> int:
        for b in self._buttons:
            if b.isChecked():
                return b.index
        return 1

    def set_current(self, index: int):
        for b in self._buttons:
            b.setChecked(b.index == index)


class SwatchButton(QAbstractButton):
    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(26, 26)
        self.setToolTip(f"第 {index} 种颜色")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = theme.course_color(self.index)
        if self.isChecked():
            ring = QPen(QColor(c.red(), c.green(), c.blue(), 90), 2)
            p.setPen(ring)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(1, 1, 24, 24))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF(4, 4, 18, 18))
            p.setPen(QColor(255, 255, 255))
            p.setFont(theme.icon_font(9, theme.QFont.Weight.Bold))
            p.drawText(QRectF(4, 4, 18, 18), Qt.AlignmentFlag.AlignCenter, theme.icon_char("check"))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            p.setBrush(c)
            p.drawEllipse(QRectF(3, 3, 20, 20))
        p.end()


# ---------------------------------------------------------------- 提示
class Toast(QWidget):
    def __init__(self, text: str, kind: str = "ok", parent=None,
                 action_label: str | None = None, on_action=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._kind = kind
        self._text = text
        self._action_label = action_label
        self._on_action = on_action
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_animated)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(160)
        self._fade_cur = 0.0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 9, 13, 9)
        lay.setSpacing(9)
        icon = QLabel(self)
        icon.setFont(theme.icon_font(15))
        icon.setFixedWidth(17)
        colors = {"ok": theme.C_GREEN, "warn": theme.C_AMBER, "err": theme.C_RED, "info": theme.C_BLUE}
        icons = {"ok": "check", "warn": "warning", "err": "warning", "info": "info"}
        icon.setStyleSheet(f"color: {colors.get(kind, theme.C_BLUE)}; background: transparent;")
        icon.setText(theme.icon_char(icons.get(kind, "info")))
        self.text_label = QLabel(text, self)
        self.text_label.setFont(theme.font(11.5))
        self.text_label.setStyleSheet("background: transparent;")
        self.text_label.setWordWrap(True)
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.text_label, 1)
        if action_label:
            act = AppButton(action_label, None, "soft", "sm")
            act.clicked.connect(self._do_action)
            lay.addWidget(act, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setObjectName("toast")
        # 深色模式下不能用白底：正文颜色是主题色（深色下为浅色字），白底会看不见。
        _dark = theme.MODE == "dark"
        _bg = "rgba(48, 54, 72, 246)" if _dark else "rgba(255, 255, 255, 248)"
        _bd = "rgba(255, 255, 255, 62)" if _dark else "rgba(255, 255, 255, 250)"
        self.setStyleSheet(
            f"#toast {{ background: {_bg}; border: 1px solid {_bd}; border-radius: 11px; }}"
        )
        self.text_label.setMinimumWidth(120)
        self.adjustSize()

    def _do_action(self):
        if self._on_action:
            try:
                self._on_action()
            except Exception:
                pass
        self.hide_animated()

    def _target_opacity(self, v):
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(v)
        self._fade.start()

    def show_at(self, rect: QRect, timeout: int = 2600):
        self.adjustSize()
        w = min(max(240, self.sizeHint().width()), 520)
        self.setFixedWidth(w)
        pad = 86 if self._action_label else 52
        self.text_label.setFixedWidth(max(120, w - pad))
        self.adjustSize()
        x = rect.left() + (rect.width() - self.width()) // 2
        y = rect.bottom() - self.height() - 26
        self.move(x, y)
        self.show()
        self.raise_()
        self._target_opacity(1.0)
        if timeout > 0:
            self._timer.start(timeout)

    def hide_animated(self):
        self._timer.stop()
        self._fade.stop()
        self._fade.setDuration(220)
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.deleteLater)
        self._fade.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 11, 11)
        if theme.MODE == "dark":
            p.fillPath(path, QColor(48, 54, 72, 248))
            p.setPen(QPen(QColor(255, 255, 255, 56), 1))
        else:
            p.fillPath(path, QColor(255, 255, 255, 248))
            p.setPen(QPen(QColor(28, 28, 30, 20), 1))
        p.drawPath(path)
        p.end()


class ToastHost(QWidget):
    """贴在主窗口底部居中的提示层。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        self._toast: Toast | None = None

    def show_message(self, text: str, kind: str = "ok", action_label: str | None = None,
                     on_action=None, timeout: int = 2600):
        if self._toast is not None:
            try:
                self._toast.deleteLater()
            except Exception:
                pass
        host = self.parentWidget()
        toast = Toast(text, kind, host, action_label, on_action)
        self._toast = toast
        rect = host.rect()
        toast.show_at(rect, timeout)


# ---------------------------------------------------------------- 弹窗
class GlassDialog(QDialog):
    def __init__(self, parent=None, width: int = 560, title: str = "",
                 subtitle: str = "", icon: str | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._drag_pos: QPoint | None = None
        self._body_width = width

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 28)
        self.card = QFrame(self)
        self.card.setObjectName("dialogCard")
        # 卡片底色随主题：深色下用深色卡片，否则卡片内浅色文字会看不见。
        _dark = theme.MODE == "dark"
        _bg = "rgba(32, 37, 52, 246)" if _dark else "rgba(255, 255, 255, 243)"
        _bd = "rgba(255, 255, 255, 58)" if _dark else "rgba(255, 255, 255, 248)"
        self.card.setStyleSheet(
            f"#dialogCard {{ background: {_bg};"
            f" border: 1px solid {_bd}; border-radius: 20px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(46)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(20, 40, 80, 58))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(24, 20, 24, 20)
        inner.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(10)
        if icon:
            badge = IconBadge(icon, 38, self.card)
            head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title_label = QLabel(title, self.card)
        self.title_label.setFont(theme.font(18, theme.QFont.Weight.DemiBold))
        self.title_label.setStyleSheet("background: transparent;")
        self.subtitle_label = QLabel(subtitle, self.card)
        self.subtitle_label.setFont(theme.font(11))
        self.subtitle_label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.subtitle_label.setVisible(bool(subtitle))
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.subtitle_label)
        head.addLayout(text_box, 1)
        close = AppButton("", "close", "ghost", "icon")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setToolTip("关闭")
        close.clicked.connect(self.reject)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        inner.addLayout(head)

        self.error_label = QLabel("", self.card)
        self.error_label.setFont(theme.font(11))
        self.error_label.setStyleSheet(
            f"color: #D70015; background: rgba(255, 59, 48, 24); border-radius: 7px; padding: 6px 9px;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        inner.addWidget(self.error_label)

        self.body = QWidget(self.card)
        self.body.setStyleSheet("background: transparent;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        inner.addWidget(self.body)

        self.footer = QHBoxLayout()
        self.footer.setSpacing(9)
        self.footer.setContentsMargins(0, 2, 0, 0)
        inner.addLayout(self.footer)

        self.setFixedWidth(width + 56)
        self.setSizeGripEnabled(False)

    def add_footer(self, widget: QWidget, stretch_before: bool = True):
        if stretch_before:
            self.footer.addStretch(1)
        self.footer.addWidget(widget)

    def add_footer_stretch(self):
        self.footer.addStretch(1)

    def show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 84:
            if self.windowHandle():
                self.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            geo = parent.window().frameGeometry()
            self.move(geo.center() - self.rect().center())


class ConfirmDialog(GlassDialog):
    def __init__(self, parent, title: str, text: str, ok_label: str = "确定",
                 danger: bool = False):
        super().__init__(parent, width=400, title=title, icon="warning")
        self.confirmed = False
        self.subtitle_label.hide()
        t = QLabel(text, self.body)
        t.setWordWrap(True)
        t.setFont(theme.font(12))
        t.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.body_layout.addWidget(t)
        cancel = AppButton("取消", None, "ghost", "md")
        cancel.clicked.connect(self.reject)
        ok = AppButton(ok_label, None, "primary" if not danger else "soft", "md")
        if danger:
            ok.kind = "danger"
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        self.add_footer(cancel)
        self.add_footer(ok)
        self.adjustSize()

    def _accept(self):
        self.confirmed = True
        self.accept()


def ask_confirm(parent, title: str, text: str, ok_label: str = "删除",
                danger: bool = True) -> bool:
    dlg = ConfirmDialog(parent, title, text, ok_label, danger)
    dlg.exec()
    return dlg.confirmed


class Divider(QFrame):
    def __init__(self, parent=None, margin_left: int = 0, margin_right: int = 0):
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)
        self._ml = margin_left
        self._mr = margin_right
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(theme.divider_style(16))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(QRect(self._ml, 0, self.width() - self._ml - self._mr, 1),
                   theme.divider_color(16))
        p.end()


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hline")
    f.setFixedHeight(1)
    f.setStyleSheet(theme.divider_style(14))
    return f


def label(text: str, size: float = 11, color: str = None,
          weight=theme.QFont.Weight.Normal, parent=None) -> QLabel:
    lab = QLabel(text, parent)
    lab.setFont(theme.font(size, weight))
    lab.setStyleSheet(f"color: {color or theme.C_SUB}; background: transparent;")
    return lab


class ElidedLabel(QLabel):
    """单行 QLabel，宽度不足时以省略号截断，完整文本放进 tooltip。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_elided()

    def full_text(self) -> str:
        return self._full_text

    def _refresh_elided(self):
        available = max(10, self.width() - 2)
        elided = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, available)
        QLabel.setText(self, elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elided()

# ---------------------------------------------------------------- 表单控件
class Select(QComboBox):
    """带自绘下箭头的下拉框（QSS 隐藏了系统箭头）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() - 16
        cy = self.height() / 2.0
        pen = QPen(QColor(theme.C_SUB), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(cx - 3.6, cy - 2.0)
        path.lineTo(cx, cy + 1.6)
        path.lineTo(cx + 3.6, cy - 2.0)
        p.drawPath(path)
        p.end()


class _TimePopup(QWidget):
    """时间选项弹出层（替代原生 QMenu）。

    原生 QMenu 在浅色主题下会渲染成全黑：Win32 原生菜单不吃应用级 QSS。
    这里自绘一个玻璃弹出层，深浅两套主题都正常，样式也和界面统一。
    """

    picked = Signal(object)  # str "HH"

    def __init__(self, parent=None, values=()):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._values = [f"{int(v):02d}" for v in values]
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._card = QWidget(self)
        self._card.setObjectName("timePopupCard")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        self.list = QListWidget(self._card)
        self.list.setFont(theme.font(13))
        self.list.setFixedWidth(92)
        self.list.setMinimumHeight(56)
        self.list.setMaximumHeight(240)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.addItems(self._values)
        for _i in range(self.list.count()):
            self.list.item(_i).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list.itemClicked.connect(self._on_pick_item)
        lay.addWidget(self.list)
        outer.addWidget(self._card)
        # 顶层 Popup 在部分平台上不按 sizeHint 收缩，这里显式定宽（92 + 内边距 + 边框）
        self.setFixedWidth(92 + 6 + 6 + 2)
        self._refresh()

    def _refresh(self):
        t = theme.tokens()
        bg = theme.card_rgba(246)
        border = theme.rgba_str(t["card_border"])
        inner = theme.card_rgba(252)
        sel = theme.rgba_str(t["card"], 205)
        thumb = "rgba(255,255,255,64)" if theme.MODE == "dark" else "rgba(28,28,30,42)"
        self._card.setStyleSheet(
            f"#timePopupCard {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 12px; }}"
        )
        self.list.setStyleSheet(
            f"QListWidget {{ background: {inner}; color: {theme.C_TEXT};"
            f" border: none; outline: 0; }}"
            f"QListWidget::item {{ padding: 5px 10px; border-radius: 6px; }}"
            f"QListWidget::item:hover {{ background: {sel}; }}"
            f"QListWidget::item:selected {{ background: {theme.C_BLUE}; color: #FFFFFF; }}"
            f"QListWidget::scrollbar:vertical {{ width: 8px; background: transparent; }}"
            f"QListWidget::scrollbar-thumb:vertical {{"
            f" background: {thumb}; border-radius: 4px; }}"
        )

    def apply_theme(self):
        self._refresh()

    def open_at(self, field, current=None):
        self.adjustSize()
        self._refresh()
        self.list.setCurrentRow(-1)
        if current:
            for _i in range(self.list.count()):
                if self.list.item(_i).text() == current:
                    self.list.setCurrentRow(_i)
                    self.list.scrollToItem(
                        self.list.item(_i), QListWidget.ScrollHint.PositionAtCenter
                    )
                    break
        p = field.mapToGlobal(QPoint(field.width(), field.height()))
        screen = QGuiApplication.screenAt(p) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = min(max(p.x() - self.width(), geo.left() + 8), geo.right() - self.width() - 8)
        y = p.y() + 4
        if y + self.height() > geo.bottom():
            y = max(geo.top() + 8, field.mapToGlobal(QPoint(0, -self.height() - 4)).y())
        self.move(x, y)
        self.show()
        self.raise_()

    def _on_pick_item(self, item):
        self.picked.emit(item.text())
        self.close()


class _TimeField(QWidget):
    """单个时间输入框：数字可直接输入，右侧下拉箭头引导点击展开。

    不用原生 QComboBox：它的可编辑行编辑宽度会被内容撑得很窄，
    数字看起来偏左且被裁切，右侧箭头也被全局 QSS 隐藏。这里自绘
    底色、边框与倒三角，文本居中，任何宽度都不裁切。
    """

    CHEVRON_W = 20
    changed = Signal(object)  # str "HH"

    def __init__(self, parent=None, values=(), label=""):
        super().__init__(parent)
        self._values = [f"{int(v):02d}" for v in values]
        self._label = label
        self._popup: _TimePopup | None = None
        lay = QHBoxLayout(self)
        # 左侧留出与右侧箭头等宽的空白，让居中数字落在整个框的正中，
        # 而不是被右侧箭头挤偏。
        lay.setContentsMargins(self.CHEVRON_W, 0, 0, 0)
        lay.setSpacing(0)

        self.line = QLineEdit()
        self.line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.line.setFont(theme.font(13))
        self.line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.line.setMaxLength(2)
        self.line.setFixedHeight(38)
        # 关键：不要给行编辑留水平内边距。QLineEdit 同时带水平 padding 与
        # AlignCenter 时，Qt 会把文本按“整宽”居中、再按“去 padding 后的窄框”
        # 裁剪，导致首字符左侧被切掉（“08”看起来像“⊃8”）。padding: 0 则严丝合缝。
        self.line.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding: 0; }"
        )
        self.line.textEdited.connect(self._on_text_edited)
        lay.addWidget(self.line, 1)

        spacer = QWidget()
        spacer.setFixedWidth(self.CHEVRON_W)
        lay.addWidget(spacer)

        self.setFixedHeight(38)
        self.setMinimumWidth(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = theme.MODE == "dark"
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 底色 + 边框（注意：QColor 不接受 "rgba(...)" 字符串，会得到无效黑色）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 22 if dark else 214))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(QPen(QColor(255, 255, 255, 54) if dark else QColor(28, 28, 30, 42), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        # 右侧引导倒三角
        cx = self.width() - self.CHEVRON_W / 2.0
        cy = self.height() / 2.0
        tri = QPolygonF()
        tri.append(QPointF(cx - 4.5, cy - 3.0))
        tri.append(QPointF(cx + 4.5, cy - 3.0))
        tri.append(QPointF(cx, cy + 3.5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.C_SUB))
        p.drawPolygon(tri)
        p.end()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.pos().x() >= self.width() - self.CHEVRON_W):
            self._open_popup()
            return
        super().mousePressEvent(event)

    def set_value(self, text: str):
        self.line.setText(text)

    def value(self) -> str:
        try:
            return f"{int(self.line.text()):02d}"
        except ValueError:
            return "00"

    def _on_text_edited(self, _text):
        self.changed.emit(self.value())

    def _open_popup(self):
        if self._popup is None:
            self._popup = _TimePopup(self, self._values)
            self._popup.picked.connect(self._pick)
        self._popup.open_at(self, self.line.text().strip())

    def apply_theme(self):
        # 底色与箭头在 paintEvent 里按 theme.MODE 现画；弹出层随主题刷新。
        self.update()
        if self._popup is not None:
            self._popup.apply_theme()

    def _pick(self, text):
        self.line.setText(text)
        self.changed.emit(self.value())


class TimePicker(QWidget):
    """时 / 分 两个输入框，点击右侧箭头展开、可直接输入，滚轮不再改动时间。"""

    changed = Signal(object)  # str "HH:MM"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.hour = _TimeField(self, range(24), "小时：点开下拉或直接输入 0–23")
        self.minute = _TimeField(self, range(0, 60, 5), "分钟：点开下拉或直接输入 0–59")
        # 关键：禁用滚轮，避免误改时间
        self.hour.installEventFilter(self)
        self.minute.installEventFilter(self)
        self.hour.line.installEventFilter(self)
        self.minute.line.installEventFilter(self)
        self.hour.changed.connect(self._emit)
        self.minute.changed.connect(self._emit)
        lay.addWidget(self.hour)
        middle = QLabel(":")
        middle.setFont(theme.font(14, theme.QFont.Weight.DemiBold))
        middle.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        lay.addWidget(middle)
        lay.addWidget(self.minute)
        self.setFixedHeight(38)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(obj, event)

    def set_time(self, text: str):
        hh, mm = (str(text).split(":") + ["0"])[:2]
        self.hour.set_value(f"{int(hh or 0):02d}")
        self.minute.set_value(f"{int(mm or 0):02d}")

    def value(self) -> str:
        try:
            h = core_clamp(int(self.hour.value() or 0), 0, 23)
        except ValueError:
            h = 0
        try:
            m = core_clamp(int(self.minute.value() or 0), 0, 59)
        except ValueError:
            m = 0
        return f"{h:02d}:{m:02d}"

    def _emit(self, _text=""):
        self.changed.emit(self.value())

    def apply_theme(self):
        # 底色与箭头在 paintEvent 里按 theme.MODE 现画，重绘即可。
        self.update()


def core_clamp(value, lo, hi):
    return max(lo, min(hi, value))


class CalendarPopup(QWidget):
    """点击日期框弹出的浅色日历。"""

    picked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._mode = theme.MODE
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        t = theme.tokens()
        card_bg = theme.card_rgba(250)
        # QCalendarWidget 内部视图不吃带 alpha 的 rgba 背景（Qt 会合成到纯黑上，
        # 整块日历变黑），所以日历自身一律用不透明底色。
        cal_bg = theme.popup_solid()
        hover = "#25314A" if theme.MODE == "dark" else "#E7F4FF"
        card_border = theme.rgba_str(t["card_border"])
        text_col = theme.C_TEXT
        blue_col = theme.C_BLUE
        card = QWidget(self)
        card.setObjectName("calendarPopupCard")
        card.setStyleSheet(
            f"#calendarPopupCard {{ background: {card_bg}; border: 1px solid {card_border};"
            f" border-radius: 14px; }}"
        )
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        self.cal = QCalendarWidget(card)
        self.cal.setGridVisible(False)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.cal.setMinimumSize(304, 250)
        pal = self.cal.palette()
        for role, value in (
            (QPalette.ColorRole.Window, cal_bg),
            (QPalette.ColorRole.Base, cal_bg),
            (QPalette.ColorRole.AlternateBase, cal_bg),
            (QPalette.ColorRole.Text, text_col),
            (QPalette.ColorRole.WindowText, text_col),
            (QPalette.ColorRole.ButtonText, text_col),
            (QPalette.ColorRole.Highlight, blue_col),
            (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        ):
            pal.setColor(role, _rgba(value) if isinstance(value, str) and value.startswith("rgba") else QColor(value))
        self.cal.setPalette(pal)
        self.cal.setStyleSheet(
            f"QCalendarWidget QWidget {{ background: {cal_bg}; }}"
            f"QCalendarWidget QAbstractItemView:enabled {{ background: {cal_bg};"
            f" color: {text_col}; selection-background-color: {blue_col};"
            f" selection-color: #FFFFFF; outline: 0; }}"
            f"QCalendarWidget QAbstractItemView:disabled {{ color: {theme.C_MUTED}; }}"
            f"QCalendarWidget QToolButton {{ background: transparent; color: {text_col};"
            f" border: none; border-radius: 6px; padding: 4px 7px; }}"
            f"QCalendarWidget QToolButton:hover {{ background: {hover}; }}"
            f"QCalendarWidget QMenu {{ background: {cal_bg}; color: {text_col}; }}"
            f"QCalendarWidget QSpinBox {{ background: {cal_bg}; color: {text_col};"
            f" selection-background-color: {blue_col}; selection-color: #FFFFFF; }}"
            f"QCalendarWidget QTableView {{ background: {cal_bg}; }}"
        )
        # 星期表头的底色只认 QTextCharFormat，QSS 的 QHeaderView::section 盖不住，
        # 深色模式下会留一条近白色的横带。
        head_fmt = QTextCharFormat()
        head_fmt.setForeground(theme.qcolor(theme.C_SUB))
        head_fmt.setBackground(theme.qcolor(cal_bg))
        self.cal.setHeaderTextFormat(head_fmt)
        lay.addWidget(self.cal)
        self.cal.clicked.connect(self._choose)

    def _choose(self, date):
        self.picked.emit(date)
        self.close()

    def open_at(self, field, date):
        self.cal.setSelectedDate(date)
        self.adjustSize()
        pos = field.mapToGlobal(QPoint(0, field.height() + 6))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = min(max(pos.x(), geo.left() + 8), geo.right() - self.width() - 8)
        y = pos.y()
        if y + self.height() > geo.bottom():
            y = field.mapToGlobal(QPoint(0, -self.height() - 6)).y()
        self.move(x, y)
        self.show()
        self.raise_()


class DateField(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(False)
        self.setDisplayFormat("yyyy-MM-dd")
        self.setMinimumHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._popup = None

    def _open_calendar(self):
        # 弹层在构造时按当时的主题着色，切主题后必须重建，否则会残留旧配色。
        if self._popup is None or getattr(self._popup, "_mode", None) != theme.MODE:
            if self._popup is not None:
                self._popup.hide()
                self._popup.deleteLater()
            self._popup = CalendarPopup(self)
            self._popup.picked.connect(self._on_picked)
        self._popup.open_at(self, self.date())

    def _on_picked(self, date):
        self.setDate(date)
        self.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_calendar()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_F4):
            self._open_calendar()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.C_SUB), 1.2)
        p.setPen(pen)
        cx = self.width() - 15
        cy = self.height() / 2
        p.drawRoundedRect(QRectF(cx - 6, cy - 5.5, 12, 11), 2.4, 2.4)
        p.drawLine(QPointF(cx - 6, cy - 1.5), QPointF(cx + 6, cy - 1.5))
        p.drawLine(QPointF(cx - 3, cy - 8), QPointF(cx - 3, cy - 6))
        p.drawLine(QPointF(cx + 3, cy - 8), QPointF(cx + 3, cy - 6))
        p.end()


class TimeField(QTimeEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("HH:mm")
        self.setMinimumHeight(38)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(theme.C_SUB), 1.2))
        cx = self.width() - 15
        cy = self.height() / 2
        p.drawEllipse(QPointF(cx, cy), 5.6, 5.6)
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - 3.2))
        p.drawLine(QPointF(cx, cy), QPointF(cx + 2.6, cy + 0.6))
        p.end()

