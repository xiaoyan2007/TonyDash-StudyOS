"""视觉基调：颜色、字体、图标、背景与玻璃卡片绘制。

风格对标参考程序 ShiGuangToDo：浅色亚克力、半透明白卡片、
iOS 蓝强调色、克制的圆角与细边框。
"""

from __future__ import annotations

import os
import sys
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QImage, QLinearGradient, QPainter,
    QPainterPath, QPen, QPolygonF, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene,
)

def asset_path(name: str) -> str:
    """定位随程序分发的静态资源（源码运行与 PyInstaller 打包都能用）。"""
    if getattr(sys, "_MEIPASS", None):
        base = os.path.join(sys._MEIPASS, "assets")
    else:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    return os.path.join(base, name)


# ---------------------------------------------------------------- 主题
LIGHT = {
    "text": "#18181B", "sub": "#5F5F66", "muted": "#85858C",
    "blue": "#0A84FF", "blue_hover": "#0A76E0", "blue_press": "#0768C8",
    "green": "#248A3D", "red": "#D70015", "amber": "#8A5200",
    "orange": "#C25E00", "purple": "#8944AB", "teal": "#0F7C8A",
    "white": "#FFFFFF",
    "card": (255, 255, 255), "card_border": (34, 52, 86, 92),
    "card_shadow": (34, 58, 104, 38), "card_highlight": (255, 255, 255, 150),
    "backdrop": ("#EDF5FF", "#DEEBFA", "#D2E2F6", "#C9D9F0"),
    "blobs": [(108, 162, 255, 116), (170, 140, 255, 72), (78, 208, 198, 64),
              (255, 178, 138, 44), (255, 255, 255, 140)],
    "grid": (60, 90, 140, 7),
}
DARK = {
    "text": "#F2F3F7", "sub": "#B9BCC7", "muted": "#9A9DA9",
    "blue": "#4C9BFF", "blue_hover": "#69ABFF", "blue_press": "#2F80E8",
    "green": "#4ADE80", "red": "#FF7B72", "amber": "#F0B259",
    "orange": "#FFB066", "purple": "#C792EA", "teal": "#5FD3DF",
    "white": "#FFFFFF",
    "card": (28, 32, 44), "card_border": (255, 255, 255, 60),
    "card_shadow": (0, 0, 0, 120), "card_highlight": (255, 255, 255, 40),
    "backdrop": ("#14161F", "#171B27", "#1B2030", "#12141C"),
    "blobs": [(58, 96, 200, 150), (110, 70, 190, 110), (30, 140, 140, 90),
              (150, 90, 60, 60), (70, 90, 160, 120)],
    "grid": (255, 255, 255, 10),
}
MODE = "light"

# ---------------------------------------------------------------- 基础色
C_TEXT = LIGHT["text"]
C_SUB = LIGHT["sub"]
C_MUTED = LIGHT["muted"]
C_BLUE = LIGHT["blue"]
C_BLUE_HOVER = LIGHT["blue_hover"]
C_BLUE_PRESS = LIGHT["blue_press"]
C_BLUE_SOFT = "rgba(10, 132, 255, 38)"
C_GREEN = LIGHT["green"]
C_RED = LIGHT["red"]
C_AMBER = LIGHT["amber"]
C_ORANGE = LIGHT["orange"]
C_PURPLE = LIGHT["purple"]
C_TEAL = LIGHT["teal"]
C_WHITE = LIGHT["white"]


def tokens() -> dict:
    return DARK if MODE == "dark" else LIGHT


def set_theme(mode: str) -> str:
    """切换全局配色，返回实际生效的模式。"""
    global MODE, C_TEXT, C_SUB, C_MUTED, C_BLUE, C_BLUE_HOVER, C_BLUE_PRESS
    global C_GREEN, C_RED, C_AMBER, C_ORANGE, C_PURPLE, C_TEAL, C_WHITE
    MODE = "dark" if mode == "dark" else "light"
    t = tokens()
    C_TEXT, C_SUB, C_MUTED = t["text"], t["sub"], t["muted"]
    C_BLUE, C_BLUE_HOVER, C_BLUE_PRESS = t["blue"], t["blue_hover"], t["blue_press"]
    C_GREEN, C_RED, C_AMBER = t["green"], t["red"], t["amber"]
    C_ORANGE, C_PURPLE, C_TEAL, C_WHITE = t["orange"], t["purple"], t["teal"], t["white"]
    return MODE

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei"


COURSE_COLORS = [
    "#0A84FF",  # 蓝
    "#5E5CE6",  # 靛
    "#30B0C7",  # 青
    "#34C759",  # 绿
    "#FF9F0A",  # 橙
    "#FF375F",  # 玫红
    "#BF5AF2",  # 紫
    "#AC8E68",  # 棕
]

# ---------------------------------------------------------------- 图标
# Segoe Fluent Icons / Segoe MDL2 Assets 码位
ICON_CODES = {
    "calendar": 0xE787, "cap": 0xE7BE, "settings": 0xE713, "plus": 0xE710,
    "search": 0xE721, "left": 0xE76B, "right": 0xE76C, "trash": 0xE74D,
    "copy": 0xE8C8, "download": 0xE896, "upload": 0xE898, "print": 0xE749,
    "close": 0xE711, "min": 0xE921, "max": 0xE922, "restore": 0xE923,
    "check": 0xE73E, "clock": 0xE823, "pin": 0xE707, "user": 0xE77B,
    "warning": 0xE7BA, "info": 0xE946, "edit": 0xE70F, "refresh": 0xE72C,
    "save": 0xE74E, "back": 0xE72B, "forward": 0xE72A, "home": 0xE80F,
    "books": 0xE8F1, "list": 0xE8FD, "report": 0xE9F9, "filter": 0xE71C,
    "more": 0xE712, "chev_down": 0xE70D, "chev_up": 0xE70E, "star": 0xE734,
    "star_fill": 0xE735, "spark": 0xE945, "flag": 0xE7C1, "done": 0xE930,
    "tag": 0xE8EC, "folder": 0xE8B7, "doc": 0xE8A5, "shuffle": 0xE8B1, "external": 0xE8A7,
}

# 这些图标用矢量绘制：不依赖字体里是否有对应字形（不同系统码位可能缺失）。
VECTOR_ICONS = ("moon", "sun", "heart", "chevron_down")


_icon_family_cache: str | None = None
_icon_font_cache: dict = {}
_font_cache: dict = {}
_backdrop_cache: dict = {}


def load_fonts() -> None:
    """加载系统字体文件。Qt 6 在无字体目录时会退化，必须显式注册。"""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "SegoeIcons.ttf",
                 "segmdl2.ttf", "seguiemj.ttf"):
        path = os.path.join(windir, "Fonts", name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


def icon_family() -> str:
    global _icon_family_cache
    if _icon_family_cache:
        return _icon_family_cache
    families = set(QFontDatabase.families())
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            _icon_family_cache = name
            return name
    _icon_family_cache = "Segoe UI Symbol"
    return _icon_family_cache


def icon_char(name: str) -> str:
    return chr(ICON_CODES.get(name, ICON_CODES["info"]))


def icon_font(size: int = 16, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    key = (icon_family(), int(size), weight)
    cached = _icon_font_cache.get(key)
    if cached is not None:
        return QFont(cached)
    f = QFont(icon_family())
    f.setPixelSize(int(size))
    f.setWeight(weight)
    _icon_font_cache[key] = f
    return QFont(f)


def vector_icon_pixmap(name: str, size: int, color) -> QPixmap:
    """用矢量绘制月亮 / 太阳，返回带透明背景的位图。

    Segoe MDL2 里月亮、太阳的码位在部分系统上缺失，直接画字形会退化成
    方框或回退成「i」。这里统一矢量绘制，任何环境都一致。
    """
    c = QColor(color)
    pm = QPixmap(max(1, int(size)), max(1, int(size)))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    s = float(size)
    if name == "moon":
        # 两个椭圆用 OddEven 填充规则叠出月牙，避开不同 PySide6 版本
        # 对 QPainter.CompositionMode 枚举命名的差异。
        r = s * 0.40
        cx, cy = s / 2.0, s / 2.0 + s * 0.03
        bite = r * 0.92
        shape = QPainterPath()
        shape.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        shape.addEllipse(QRectF(cx + r * 0.42 - bite, cy - r * 0.14 - bite,
                                2 * bite, 2 * bite))
        shape.setFillRule(Qt.FillRule.OddEvenFill)
        p.fillPath(shape, c)
    elif name == "sun":
        r = s * 0.22
        cx = cy = s / 2.0
        p.drawEllipse(QPointF(cx, cy), r, r)
        for i in range(8):
            a = math.radians(i * 45.0)
            p.drawLine(
                QPointF(cx + r * 1.45 * math.cos(a), cy + r * 1.45 * math.sin(a)),
                QPointF(cx + r * 2.02 * math.cos(a), cy + r * 2.02 * math.sin(a)))
    elif name == "heart":
        # 两圆 + 下方三角拼成的心形
        r = s * 0.34
        cx = s / 2.0
        cy = s * 0.42
        p.drawEllipse(QPointF(cx - r * 0.62, cy - r * 0.62), r, r)
        p.drawEllipse(QPointF(cx + r * 0.62, cy - r * 0.62), r, r)
        tri = QPolygonF()
        tri.append(QPointF(cx - s * 0.42, cy + r * 0.18))
        tri.append(QPointF(cx + s * 0.42, cy + r * 0.18))
        tri.append(QPointF(cx, cy + s * 0.62))
        p.drawPolygon(tri)
    elif name == "chevron_down":
        # 下拉引导箭头（等腰三角），用于输入框右侧提示可点击
        tri = QPolygonF()
        tri.append(QPointF(s * 0.16, s * 0.40))
        tri.append(QPointF(s * 0.84, s * 0.40))
        tri.append(QPointF(s * 0.50, s * 0.84))
        p.drawPolygon(tri)
    p.end()
    return pm


# emoji 图标：用户要求右上角主题按钮用真正的 emoji 月亮 / 太阳。
# Segoe UI Emoji 在 Windows 上随系统自带，字形是彩色的，辨识度远高于矢量图标。
EMOJI_FONT_FAMILY = "Segoe UI Emoji"
EMOJIS = {
    "moon": "\U0001F319",        # 🌙 峨眉月
    "sun": "☀️",      # ☀️ 太阳
    "heart": "\U0001F49B",       # 💕
}
_emoji_font_cache: dict = {}


def emoji_font(size: int = 16) -> QFont:
    key = max(12, int(size))
    cached = _emoji_font_cache.get(key)
    if cached is not None:
        return QFont(cached)
    families = set(QFontDatabase.families())
    fam = EMOJI_FONT_FAMILY if EMOJI_FONT_FAMILY in families else FONT_FAMILY
    f = QFont(fam)
    f.setPixelSize(key)
    _emoji_font_cache[key] = f
    return QFont(f)


def emoji_char(name: str) -> str:
    return EMOJIS.get(name, EMOJIS["moon"])


def rgba_str(rgba, alpha: int | None = None) -> str:
    """把 (r, g, b[, a]) 元组转成 QSS 安全的 rgba() 字符串。

    注意：QColor 不接受 "rgba(...)" 字符串（会得到无效黑色），
    但 QSS 里 rgba() 是合法写法，所以样式表统一用这个函数生成。
    """
    r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
    a = int(rgba[3]) if len(rgba) > 3 and rgba[3] is not None else 255
    if alpha is not None:
        a = max(0, min(255, int(alpha)))
    return f"rgba({r}, {g}, {b}, {a})"


def card_rgba(alpha: int) -> str:
    """当前主题卡片底色的 rgba 字符串。"""
    return rgba_str(tokens()["card"], alpha)


def popup_solid() -> str:
    """弹层的不透明底色（十六进制）。

    QCalendarWidget 的内部视图在 QSS 里若拿到带 alpha 的 rgba() 背景，
    Qt 会把它合成到纯黑上（实测整块日历变 #000000），因此日历相关
    的样式必须用不透明颜色。
    """
    return "#1E222E" if MODE == "dark" else "#FFFFFF"


def qcolor(value) -> QColor:
    """把 'rgba(r, g, b, a)' 字符串或 QColor 转成 QColor。

    QColor 直接吃 "rgba(...)" 字符串会得到无效黑色，所以统一走这里。
    """
    if isinstance(value, QColor):
        return value
    text = str(value).strip()
    if text.startswith("rgba("):
        inner = text[text.index("(") + 1:text.rindex(")")]
        parts = [int(float(x.strip())) for x in inner.split(",")]
        if len(parts) == 4:
            return QColor(parts[0], parts[1], parts[2], parts[3])
        return QColor(parts[0], parts[1], parts[2])
    return QColor(text)


def divider_color(alpha: int = 16) -> QColor:
    """分隔线颜色：浅色下用深色淡线，深色下必须换成浅色淡线，否则整条线看不见。"""
    if MODE == "dark":
        return QColor(255, 255, 255, max(22, min(90, alpha + 12)))
    return QColor(28, 28, 30, alpha)


def divider_style(alpha: int = 16) -> str:
    c = divider_color(alpha)
    return f"background: rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()});"


def font(size: int = 13, weight: QFont.Weight = QFont.Weight.Normal,
         family: str | None = None, spacing: float | None = None) -> QFont:
    """返回 QFont。带缓存：界面里同一字号会被反复创建，缓存后明显省时。"""
    key = (int(size), weight, family or FONT_FAMILY, spacing)
    cached = _font_cache.get(key)
    if cached is not None:
        return QFont(cached)
    f = QFont(family or FONT_FAMILY)
    f.setPixelSize(int(size))
    f.setWeight(weight)
    if spacing is not None:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    _font_cache[key] = f
    return QFont(f)


def app_font() -> QFont:
    f = font(13)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


# ---------------------------------------------------------------- 颜色工具
def color(hex_or_color, alpha: int | None = None) -> QColor:
    c = QColor(hex_or_color) if isinstance(hex_or_color, str) else QColor(hex_or_color)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def course_color(index: int) -> QColor:
    return color(COURSE_COLORS[(max(1, int(index)) - 1) % len(COURSE_COLORS)])


def mix(a: QColor, b: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        int(a.red() + (b.red() - a.red()) * ratio),
        int(a.green() + (b.green() - a.green()) * ratio),
        int(a.blue() + (b.blue() - a.blue()) * ratio),
        int(a.alpha() + (b.alpha() - a.alpha()) * ratio),
    )


# ---------------------------------------------------------------- 背景
def _blur_pixmap(pm: QPixmap, radius: float) -> QPixmap:
    if radius <= 0.2:
        return pm
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pm)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(p, QRectF(0, 0, pm.width(), pm.height()), QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    scene.clear()
    return out


def build_backdrop(size: QSize, glass: int = 70) -> QPixmap:
    """极浅蓝白渐变 + 柔光色团，得到可承载半透明卡片的亚克力底。"""
    w, h = max(80, size.width()), max(80, size.height())
    key = (w, h, int(glass), MODE)
    cached = _backdrop_cache.get(key)
    if cached is not None:
        return cached
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    t = tokens()
    grad = QLinearGradient(0, 0, w * 0.85, h)
    stops = t["backdrop"]
    for pos, color_text in zip((0.0, 0.38, 0.72, 1.0), stops):
        grad.setColorAt(pos, QColor(color_text))
    p.fillRect(0, 0, w, h, grad)

    positions = [(0.08, 0.00, 0.70), (0.96, 0.10, 0.56), (0.80, 1.00, 0.62),
                 (0.10, 0.92, 0.50), (0.52, 0.46, 0.42)]
    blobs = [(fx, fy, fr, QColor(*rgba)) for (fx, fy, fr), rgba in zip(positions, t["blobs"])]
    for fx, fy, fr, col in blobs:
        cx, cy, r = w * fx, h * fy, max(w, h) * fr
        rg = QRadialGradient(QPointF(cx, cy), r)
        rg.setColorAt(0.0, col)
        mid = QColor(col)
        mid.setAlpha(int(col.alpha() * 0.45))
        rg.setColorAt(0.55, mid)
        end = QColor(col)
        end.setAlpha(0)
        rg.setColorAt(1.0, end)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), r, r)

    # 极细网格，增强“玻璃后面有东西”的质感
    grid = QPen(QColor(*t["grid"]))
    grid.setWidthF(1.0)
    p.setPen(grid)
    step = 44
    for x in range(0, w, step):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, step):
        p.drawLine(0, y, w, y)
    p.end()

    radius = 0.0 if glass <= 0 else 4.0 + (int(glass) / 100.0) * 32.0
    result = _blur_pixmap(pm, radius)
    _backdrop_cache[key] = result
    while len(_backdrop_cache) > 4:
        # dict 保序：pop 最早的键（等价 OrderedDict.popitem(last=False)）
        _backdrop_cache.pop(next(iter(_backdrop_cache)))
    return result


def paint_glass(p: QPainter, rect: QRectF, radius: float = 16,
                alpha: int = 150, border_alpha: int = 225,
                highlight: bool = True) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    t = tokens()
    path = QPainterPath()
    shadow = QPainterPath()
    shadow.addRoundedRect(rect.adjusted(0.5, 4.0, -0.5, 2.0), radius, radius)
    p.fillPath(shadow, QColor(*t["card_shadow"]))
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    card = t["card"]
    p.fillPath(path, QColor(card[0], card[1], card[2], alpha))
    border = t["card_border"]
    pen = QPen(QColor(border[0], border[1], border[2], int(border[3] * border_alpha / 225)))
    pen.setWidthF(1.0)
    p.setPen(pen)
    p.drawPath(path)
    if highlight:
        hl = QPen(QColor(*t["card_highlight"]))
        hl.setWidthF(1.0)
        p.setPen(hl)
        p.drawLine(QPointF(rect.left() + radius, rect.top() + 1.2),
                   QPointF(rect.right() - radius, rect.top() + 1.2))
    p.restore()


# ---------------------------------------------------------------- 全局样式
QSS = """
QWidget {
    color: $TEXT;
}
QMainWindow, QDialog {
    background: transparent;
}
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QDoubleSpinBox,
QTextEdit, QPlainTextEdit {
    background: $FIELD;
    border: 1px solid $FIELD_BORDER;
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 24px;
    color: $TEXT;
    selection-background-color: $BLUE;
    selection-color: #FFFFFF;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QTextEdit:hover {
    border-color: $FIELD_BORDER_HOVER;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid $BLUE_FOCUS;
    background: $FIELD_FOCUS;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: $SUB;
    background: $FIELD_DISABLED;
}
QComboBox { padding-right: 24px; }
QComboBox::drop-down {
    border: none;
    width: 18px;
    background: transparent;
}
QComboBox::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}
QComboBox QAbstractItemView {
    background: $POPUP;
    border: 1px solid $POPUP_BORDER;
    border-radius: 10px;
    padding: 5px;
    outline: none;
    selection-background-color: rgba(10, 132, 255, 36);
    selection-color: $TEXT;
}
QComboBox QAbstractItemView::item {
    min-height: 27px;
    padding: 2px 10px;
    border-radius: 6px;
}
QDateEdit::drop-down, QTimeEdit::drop-down {
    width: 20px;
    border: none;
    background: transparent;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0px;
    border: none;
}
QTextEdit, QPlainTextEdit {
    padding: 8px 10px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollArea QWidget#qt_scrollarea_viewport {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 2px 1px;
}
QScrollBar::handle:vertical {
    background: $SCROLL;
    border-radius: 4px;
    min-height: 34px;
}
QScrollBar::handle:vertical:hover {
    background: $SCROLL_HOVER;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 9px;
}
QScrollBar::handle:horizontal {
    background: $SCROLL;
    border-radius: 4px;
    min-width: 34px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: $GROOVE;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: $BLUE;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 20px;
    height: 20px;
    margin: -7px 0;
    border-radius: 10px;
    background: #FFFFFF;
    border: 2px solid $BLUE;
}
QToolTip {
    background: $POPUP;
    color: $TEXT;
    border: 1px solid $POPUP_BORDER;
    border-radius: 8px;
    padding: 7px 10px;
}
QMenu {
    background: $POPUP;
    border: 1px solid $POPUP_BORDER;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 22px 7px 14px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: $MENU_SELECT;
}
QMenu::separator {
    height: 1px;
    background: $MENU_SEPARATOR;
    margin: 5px 8px;
}
QCalendarWidget QWidget {
    background: $POPUP_SOLID;
    color: $TEXT;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: $POPUP_SOLID;
}
QCalendarWidget QToolButton {
    color: $TEXT;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
}
QCalendarWidget QToolButton:hover {
    background: $POPUP_HOVER;
}
QCalendarWidget QMenu {
    background: $POPUP_SOLID;
    color: $TEXT;
    border: 1px solid rgba(28, 28, 30, 20);
}
QCalendarWidget QSpinBox {
    background: $POPUP_SOLID;
    color: $TEXT;
    border: 1px solid rgba(28, 28, 30, 28);
    border-radius: 6px;
    selection-background-color: $BLUE;
    selection-color: #FFFFFF;
}
QCalendarWidget QAbstractItemView:enabled {
    background: $POPUP_SOLID;
    color: $TEXT;
    selection-background-color: $BLUE;
    selection-color: #FFFFFF;
    outline: 0;
}
QCalendarWidget QAbstractItemView:disabled {
    color: $SUB;
}
QCalendarWidget QTableView {
    background: $POPUP_SOLID;
    border: none;
}
QCalendarWidget QHeaderView::section {
    background: $POPUP_SOLID;
    color: $SUB;
    border: none;
    padding: 4px 0;
}
QCheckBox, QRadioButton {
    spacing: 7px;
}
QMessageBox {
    background: #FFFFFF;
}
"""


def global_qss() -> str:
    dark = MODE == "dark"
    if dark:
        extra = {
            "$FIELD": "rgba(255, 255, 255, 22)",
            "$FIELD_BORDER": "rgba(255, 255, 255, 54)",
            "$FIELD_BORDER_HOVER": "rgba(255, 255, 255, 92)",
            "$FIELD_FOCUS": "rgba(255, 255, 255, 36)",
            "$FIELD_DISABLED": "rgba(255, 255, 255, 10)",
            "$BLUE_FOCUS": "rgba(76, 155, 255, 220)",
            "$POPUP": "rgba(30, 34, 46, 252)",
            "$POPUP_SOLID": "#1E222E",
            "$POPUP_HOVER": "#25314A",
            "$POPUP_BORDER": "rgba(255, 255, 255, 60)",
            "$SCROLL": "rgba(255, 255, 255, 60)",
            "$SCROLL_HOVER": "rgba(255, 255, 255, 110)",
            "$GROOVE": "rgba(255, 255, 255, 40)",
            "$MENU_SELECT": "rgba(76, 155, 255, 60)",
            "$MENU_SEPARATOR": "rgba(255, 255, 255, 40)",
        }
    else:
        extra = {
            "$FIELD": "rgba(255, 255, 255, 214)",
            "$FIELD_BORDER": "rgba(28, 28, 30, 42)",
            "$FIELD_BORDER_HOVER": "rgba(28, 28, 30, 72)",
            "$FIELD_FOCUS": "rgba(255, 255, 255, 242)",
            "$FIELD_DISABLED": "rgba(255, 255, 255, 110)",
            "$BLUE_FOCUS": "rgba(10, 132, 255, 220)",
            "$POPUP": "rgba(255, 255, 255, 250)",
            "$POPUP_SOLID": "#FFFFFF",
            "$POPUP_HOVER": "#E7F4FF",
            "$POPUP_BORDER": "rgba(28, 28, 30, 22)",
            "$SCROLL": "rgba(28, 28, 30, 42)",
            "$SCROLL_HOVER": "rgba(28, 28, 30, 82)",
            "$GROOVE": "rgba(28, 28, 30, 30)",
            "$MENU_SELECT": "rgba(10, 132, 255, 30)",
            "$MENU_SEPARATOR": "rgba(28, 28, 30, 16)",
        }
    out = QSS
    # 先替换更长的占位符：否则 "$FIELD" 会抢先命中 "$FIELD_BORDER"，
    # 把后者变成 "rgba(...)_BORDER" 这种无效颜色。
    for key, value in sorted(extra.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(key, value)
    return (out
            .replace("$TEXT", C_TEXT)
            .replace("$SUB", C_SUB)
            .replace("$BLUE", C_BLUE)
            .replace("$FONT", FONT_FAMILY))


_APP_ICON_CACHE: dict = {}
_APPLIED_QSS_MODE: str | None = None


def apply_global_qss(force: bool = False) -> None:
    """把全局样式表写到 QApplication；只有模式变化时才真正重设。

    Qt 每次 setStyleSheet 都会重刷整个控件树，窗口/弹窗反复创建时
    （例如自动化测试）成本会线性累积，因此这里按模式缓存。
    """
    global _APPLIED_QSS_MODE
    if not force and _APPLIED_QSS_MODE == MODE:
        return
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    app.setStyleSheet(global_qss())
    _APPLIED_QSS_MODE = MODE


def app_icon(size: int = 64) -> QIcon:
    """程序图标：蓝色圆角方块 + 学士帽。按尺寸缓存。"""
    size = max(16, int(size))
    cached = _APP_ICON_CACHE.get(size)
    if cached is not None:
        return cached
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.27, size * 0.27)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#3D9BFF"))
    grad.setColorAt(1.0, QColor("#0A6BE0"))
    p.fillPath(path, grad)
    p.setFont(icon_font(size * 0.52))
    p.setPen(QColor(255, 255, 255, 245))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, icon_char("cap"))
    p.end()
    _APP_ICON_CACHE[size] = QIcon(pm)
    return _APP_ICON_CACHE[size]
