"""TonyDash 启动动画：深色科技感、光晕网格、LOGO + 开发者头像 + 版本号。

设计参考 Photoshop CC2026 的启动页：深色底、流动光团、细网格、粒子，
LOGO 带光晕与旋转虚线环，下方依次是软件名、版本号、开发者头像，
以及一句激励学习的文案与底部进度条。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import core, theme


def _smoothstep(t: float, a: float, b: float) -> float:
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return x * x * (3.0 - 2.0 * x)


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - min(1.0, max(0.0, t))) ** 2


class SplashScreen(QWidget):
    """短时启动动画窗口，结束后自动关闭并发出 finished。"""

    finished = Signal()

    QUOTES = (
        "把课表、考试和待办，收进一块玻璃里。",
        "每一次点亮屏幕，都是向期末更近一步。",
        "今日的每一节自习，都在为未来的自己铺路。",
    )

    def __init__(self, duration_ms: int = 3000, parent=None):
        flags = (Qt.WindowType.SplashScreen
                 | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._duration = max(800, int(duration_ms))
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._orbs = [
            {"fx": 0.18, "fy": 0.22, "sx": 0.05, "sy": 0.04, "r": 0.42,
             "hue": (64, 120, 255)},
            {"fx": 0.82, "fy": 0.18, "sx": -0.04, "sy": 0.05, "r": 0.36,
             "hue": (120, 96, 255)},
            {"fx": 0.88, "fy": 0.82, "sx": -0.05, "sy": -0.03, "r": 0.46,
             "hue": (0, 206, 214)},
            {"fx": 0.12, "fy": 0.86, "sx": 0.05, "sy": -0.04, "r": 0.38,
             "hue": (255, 120, 176)},
        ]
        self._particles = [
            {"fx": 0.08 * (i + 1) % 1.0, "fy": 1.0 - (i % 7) * 0.14,
             "s": 0.10 + (i % 5) * 0.03, "a": 0.35 + (i % 4) * 0.16}
            for i in range(26)
        ]
        self._tags = ["背单词", "刷真题", "复习错题", "整理笔记", "定计划"]
        self._avatar = QPixmap(theme.asset_path("github_avatar.png"))
        self._logo = theme.app_icon(160).pixmap(160, 160)
        self._quote = self.QUOTES[0]
        self.resize(580, 430)
        self.setWindowTitle(core.APP_NAME)
        self.setWindowIcon(theme.app_icon(256))
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------ 生命周期
    def _tick(self):
        if self._elapsed.elapsed() >= self._duration:
            self._timer.stop()
            self.finished.emit()
            self.close()
            return
        self.update()

    def show_centered(self):
        """在屏幕中央显示。"""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        g = screen.availableGeometry()
        self.move(g.center() - QPointF(self.width() / 2.0, self.height() / 2.0).toPoint())
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        t = self._elapsed.elapsed() / 1000.0
        total = self._duration / 1000.0

        # 背景
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#070B16"))
        grad.setColorAt(0.55, QColor("#0B1126"))
        grad.setColorAt(1.0, QColor("#04070E"))
        p.fillRect(QRectF(0, 0, w, h), grad)

        self._draw_grid(p, w, h, t)
        self._draw_orbs(p, w, h, t)
        self._draw_particles(p, w, h, t)
        self._draw_tag_pills(p, w, h, t)

        alpha = 1.0 - _smoothstep(t, max(0.0, total - 0.5), total)
        if alpha <= 0.001:
            p.end()
            return
        p.setOpacity(alpha)

        cx = w / 2.0
        # 各要素按固定纵坐标分层，LOGO / 软件名 / 开发者信息互不重叠
        ly_logo = 106.0
        ly_name = 186.0
        ly_div = 218.0
        ly_version = 234.0
        ly_dev = 282.0
        ly_quote = 350.0
        self._draw_logo(p, cx, ly_logo, t)
        self._draw_name(p, cx, ly_name, t, w)
        self._draw_divider(p, w, ly_div, t)
        self._draw_version_row(p, cx, ly_version, ly_dev, t, w)
        self._draw_quote(p, cx, ly_quote, t, w)
        self._draw_progress(p, w, h, t)
        p.end()

    def _draw_grid(self, p, w, h, t):
        p.save()
        p.setPen(QPen(QColor(120, 160, 255, 22), 1))
        step = 38
        off = (t * 26) % step
        for x in range(-step, int(w) + step, step):
            p.drawLine(x - off, 0, x - off - 60, h)
        for y in range(0, int(h) + step, step):
            p.drawLine(0, y, w, y)
        # 中心径向辉光
        cx, cy = w / 2.0, h / 2.0 - 40
        rg = QRadialGradient(QPointF(cx, cy), min(w, h) * 0.75)
        rg.setColorAt(0.0, QColor(20, 60, 140, 90))
        rg.setColorAt(0.5, QColor(20, 44, 110, 45))
        rg.setColorAt(1.0, QColor(20, 30, 80, 0))
        p.setBrush(rg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), min(w, h) * 0.75, min(w, h) * 0.75)
        p.restore()

    def _draw_orbs(self, p, w, h, t):
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i, orb in enumerate(self._orbs):
            fx = orb["fx"] + math.sin(t * 0.45 + i * 1.7) * orb["sx"]
            fy = orb["fy"] + math.cos(t * 0.38 + i * 2.1) * orb["sy"]
            cx, cy = w * fx, h * fy
            r = min(w, h) * orb["r"]
            hue = orb["hue"]
            rg = QRadialGradient(QPointF(cx, cy), r)
            rg.setColorAt(0.0, QColor(hue[0], hue[1], hue[2], 92))
            rg.setColorAt(0.5, QColor(hue[0], hue[1], hue[2], 38))
            rg.setColorAt(1.0, QColor(hue[0], hue[1], hue[2], 0))
            p.setBrush(rg)
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.restore()

    def _draw_particles(self, p, w, h, t):
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i, part in enumerate(self._particles):
            y = (part["fy"] * h - t * part["s"] * h * 0.14) % (h + 24)
            if y < 0:
                y += h + 24
            x = part["fx"] * w + math.sin(t * 0.7 + i) * 12
            a = part["a"] * (0.55 + 0.45 * math.sin(t * 1.6 + i * 0.8))
            p.setBrush(QColor(140, 180, 255, int(a * 255)))
            p.drawEllipse(QPointF(x, y), 1.6, 1.6)
        p.restore()

    def _draw_tag_pills(self, p, w, h, t):
        """几枚向上飘动的学习标签，作为激励学习的元素。"""
        p.save()
        for i, tag in enumerate(self._tags):
            base = 0.42 + i * 0.13
            ph = (t - base) % 1.6
            if ph < 0 or ph > 1.6:
                ph = (t + i * 0.31) % 1.6
            y = h * 0.92 - ph * h * 0.62
            if y < -30:
                continue
            x = w * (0.18 + i * 0.16) + math.sin(t * 0.9 + i) * 8
            alpha = _smoothstep(ph, 0.0, 0.18) * (1.0 - _smoothstep(ph, 1.25, 1.6)) * 0.55
            if alpha <= 0.02:
                continue
            p.setOpacity(alpha)
            path = QPainterPath()
            tw = 62
            path.addRoundedRect(QRectF(x - tw / 2.0, y - 12, tw, 24), 12, 12)
            p.setBrush(QColor(90, 130, 255, int(150 * alpha / 0.55)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.setOpacity(1.0)
            f = QFont(theme.FONT_FAMILY)
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor(210, 230, 255, int(220 * alpha / 0.55)))
            p.drawText(QRectF(x - tw / 2.0, y - 12, tw, 24),
                       Qt.AlignmentFlag.AlignCenter, tag)
        p.restore()

    def _draw_logo(self, p, cx, cy, t):
        """画 LOGO：严格居中于圆心，方块内接在圆环内。"""
        size = 96.0
        a = _smoothstep(t, 0.15, 0.95)
        if a <= 0.01:
            return
        scale = 0.82 + 0.18 * _ease_out(min(1.0, max(0.0, (t - 0.15) / 0.5)))
        r = size * 0.5 * scale            # 圆环半径
        # 外圈光晕脉冲
        pulse = 0.5 + 0.5 * math.sin(t * 2.4)
        rg = QRadialGradient(QPointF(cx, cy), r * 1.9)
        rg.setColorAt(0.0, QColor(64, 140, 255, int(120 * a)))
        rg.setColorAt(0.6, QColor(64, 110, 255, int(40 * a)))
        rg.setColorAt(1.0, QColor(64, 90, 255, 0))
        p.setBrush(rg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r * 1.9, r * 1.9)
        # 旋转虚线环（位于圆环外侧）
        p.save()
        p.translate(cx, cy)
        p.rotate(t * 28.0)
        pen = QPen(QColor(130, 175, 255, int(200 * a)), 1.6)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 8])
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), r * 1.62, r * 1.62)
        p.restore()
        # 可见圆环（LOGO 就在圆心正中）
        p.setOpacity(a)
        ring_pen = QPen(QColor(150, 185, 255, int(235 * a)), 2.2)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # LOGO：尺寸内接于圆环（对角线半径 = side/√2 < r），严格居中
        logo_s = int(r * 1.32)
        pm = self._logo.scaled(logo_s, logo_s,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(QPointF(cx - pm.width() / 2.0, cy - pm.height() / 2.0), pm)
        p.setOpacity(1.0)
        # 下方扫光
        sweep = (t * 0.55) % 1.0
        if sweep < 0.28:
            sx = cx - r * 1.2 + sweep * r * 3.4
            sp = QPainterPath()
            sp.addRoundedRect(QRectF(sx - 8, cy - r * 1.0, 16, r * 2.0), 8, 8)
            p.setBrush(QColor(180, 215, 255, int(70 * a * (1 - sweep / 0.28))))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(sp)

    def _draw_name(self, p, cx, y, t, w):
        a = _smoothstep(t, 0.8, 1.45)
        if a <= 0.01:
            return
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(30)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, int(255 * a)))
        p.drawText(QRectF(0, y - 15, w, 30), Qt.AlignmentFlag.AlignCenter, core.APP_NAME)

    def _draw_version_row(self, p, cx, y_version, y_dev, t, w):
        a = _smoothstep(t, 1.05, 1.65)
        if a <= 0.01:
            return
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(12.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(120, 190, 255, int(235 * a)))
        p.drawText(QRectF(0, y_version - 8, w, 16), Qt.AlignmentFlag.AlignCenter,
                   f"{core.APP_VERSION}  ·  {core.APP_RELEASE_DATE}")

        # 开发者头像 + 名字（与上方版本号之间留出明确间距）
        av = 30.0
        ax = cx - (138 + av) / 2.0 + av / 2.0
        cy = y_dev
        ring = QPainterPath()
        ring.addEllipse(QRectF(ax - av / 2.0 - 2, cy - av / 2.0 - 2,
                               av + 4, av + 4))
        p.setBrush(QColor(90, 150, 255, int(70 * a)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(ring)
        if not self._avatar.isNull():
            src = self._avatar.scaled(int(av), int(av),
                                      Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
            mask = QPainterPath()
            mask.addEllipse(QRectF(ax - av / 2.0, cy - av / 2.0, av, av))
            clip = QPainterPath(mask)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(QPointF(ax - src.width() / 2.0, cy - src.height() / 2.0), src)
            p.restore()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(140, 185, 255, int(200 * a)), 1.6))
            p.drawPath(mask)
        text_x = ax + av / 2.0 + 12
        f2 = QFont(theme.FONT_FAMILY)
        f2.setPixelSize(12)
        f2.setWeight(QFont.Weight.DemiBold)
        p.setFont(f2)
        p.setPen(QColor(225, 235, 255, int(240 * a)))
        p.drawText(QRectF(text_x, cy - 16, w, 15), Qt.AlignmentFlag.AlignLeft, core.APP_AUTHOR)
        f3 = QFont(theme.FONT_FAMILY)
        f3.setPixelSize(10.5)
        p.setFont(f3)
        p.setPen(QColor(140, 170, 215, int(210 * a)))
        p.drawText(QRectF(text_x, cy + 1, w, 13), Qt.AlignmentFlag.AlignLeft,
                   "github.com/xiaoyan2007")

    def _draw_divider(self, p, w, y, t):
        a = _smoothstep(t, 1.0, 1.6)
        if a <= 0.01:
            return
        p.setPen(QPen(QColor(120, 170, 240, int(90 * a)), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(w / 2.0 - 110.0, y), QPointF(w / 2.0 + 110.0, y))

    def _draw_quote(self, p, cx, y, t, w):
        a = _smoothstep(t, 1.75, 2.35)
        if a <= 0.01:
            return
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(11.5)
        p.setFont(f)
        p.setPen(QColor(150, 185, 235, int(220 * a)))
        p.drawText(QRectF(0, y - 8, w, 16), Qt.AlignmentFlag.AlignCenter, self._quote)

    def _draw_progress(self, p, w, h, t):
        prog = _smoothstep(t, 1.5, 2.55)
        if prog <= 0.01:
            return
        bw = min(320.0, w * 0.62)
        bx, by = w / 2.0 - bw / 2.0, h - 34
        bh = 3.0
        p.setBrush(QColor(255, 255, 255, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bx, by, bw, bh), bh / 2.0, bh / 2.0)
        if prog > 0.001:
            grad = QLinearGradient(bx, 0, bx + bw * prog, 0)
            grad.setColorAt(0.0, QColor(80, 150, 255))
            grad.setColorAt(1.0, QColor(0, 220, 230))
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(bx, by, bw * prog, bh), bh / 2.0, bh / 2.0)
        # 版本号底部的加载提示
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(9.5)
        p.setFont(f)
        p.setPen(QColor(110, 145, 190, int(170 * _smoothstep(t, 1.2, 1.7))))
        label = "正在准备你的学习面板…" if prog < 0.999 else "准备完成"
        p.drawText(QRectF(0, by - 20, w, 14), Qt.AlignmentFlag.AlignCenter, label)
