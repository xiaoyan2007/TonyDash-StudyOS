"""样式预览：离屏渲染一屏组件，供视觉检查。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from campus_planner import theme, widgets  # noqa: E402


class Board(QWidget):
    def __init__(self):
        super().__init__()
        self.resize(1180, 760)
        self._bg = theme.build_backdrop(self.size(), 70)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        mark = widgets.IconBadge("cap", 30)
        head.addWidget(mark)
        title = QLabel("课表 · 期末")
        title.setFont(theme.font(16, theme.QFont.Weight.DemiBold))
        head.addWidget(title)
        head.addStretch(1)
        for ic in ("min", "max", "close"):
            head.addWidget(widgets.AppButton("", ic, "ghost", "icon"))
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(10)
        rail = widgets.GlassCard(radius=18, alpha=168)
        rail.setFixedWidth(210)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(10, 14, 10, 14)
        for ic, txt, checked in (("calendar", "课程表", True), ("report", "期末考试", False), ("settings", "设置", False)):
            b = widgets.NavButton(ic, txt)
            b.setChecked(checked)
            b.set_count(10 if ic == "calendar" else 5 if ic == "report" else 0)
            rl.addWidget(b)
        rl.addStretch(1)
        body.addWidget(rail)

        main = widgets.GlassCard(radius=18, alpha=158)
        ml = QVBoxLayout(main)
        ml.setContentsMargins(24, 20, 24, 20)
        ml.setSpacing(12)
        eyebrow = widgets.label("2026–2027 秋季学期 · 第 9 周", 10.5, theme.C_BLUE, theme.QFont.Weight.DemiBold)
        ml.addWidget(eyebrow)
        h = QLabel("课程表")
        h.setFont(theme.font(27, theme.QFont.Weight.Bold))
        ml.addWidget(h)
        row = QHBoxLayout()
        row.addWidget(widgets.Chip("今天 3 门课", "accent", "clock"))
        row.addWidget(widgets.Chip("第 9 周", "neutral"))
        row.addWidget(widgets.Chip("冲突 1", "amber", "warning"))
        row.addStretch(1)
        sb = widgets.SearchBox("搜索课程、老师、地点"); sb.setMinimumWidth(230); row.addWidget(sb)
        row.addWidget(widgets.AppButton("新增课程", "plus", "primary"))
        ml.addLayout(row)
        sw = widgets.Switch(checked=True)
        row2 = QHBoxLayout()
        row2.addWidget(widgets.label("显示周末", 11))
        row2.addWidget(sw)
        row2.addStretch(1)
        ml.addLayout(row2)

        stats = QHBoxLayout()
        for cap, val, unit in (("待考科目", "5", "门"), ("待考总学分", "20", "学分"), ("最近一场", "16", "天")):
            stats.addWidget(widgets.StatTile(cap, val, unit))
        ml.addLayout(stats)

        card = widgets.GlassCard(radius=14, alpha=142)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.addWidget(widgets.label("高等数学 A（下）", 15, theme.C_TEXT, theme.QFont.Weight.DemiBold))
        cl.addWidget(widgets.label("张伟 · 教二-201 · 周一 08:00–09:40", 11, theme.C_SUB))
        pb = widgets.ProgressBar(62)
        cl.addWidget(pb)
        chips = QHBoxLayout()
        for txt, kind in (("闭卷", "accent"), ("5 学分", "neutral"), ("座位 A-12", "white")):
            chips.addWidget(widgets.Chip(txt, kind))
        chips.addStretch(1)
        cl.addLayout(chips)
        ml.addWidget(card)
        ml.addStretch(1)
        body.addWidget(main, 1)
        root.addLayout(body, 1)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        p.setClipPath(path)
        p.drawPixmap(0, 0, self._bg)
        p.setClipping(False)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawPath(path)
        p.end()


def main():
    app = QApplication([])
    theme.load_fonts()
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.global_qss())
    board = Board()
    board.show()
    app.processEvents()
    out = Path(__file__).resolve().parent / "_shots" / "style1.png"
    out.parent.mkdir(exist_ok=True)
    board.grab().save(str(out))
    print("saved", out)


if __name__ == "__main__":
    main()
