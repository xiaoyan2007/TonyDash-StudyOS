"""首次启动的三步上手引导（方案一：Coach Mark）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme, widgets


class _Step:
    def __init__(self, page: int, target, title: str, body: str, tip: str):
        self.page = page
        self.target = target
        self.title = title
        self.body = body
        self.tip = tip


class CoachOverlay(QWidget):
    """半透明遮罩 + 高亮目标控件 + 说明气泡。"""

    finished = Signal(bool)  # True = 走完三步，False = 跳过

    MARGIN = 6

    def __init__(self, window: QWidget, steps, parent=None):
        super().__init__(parent or window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self._steps = list(steps)
        self._index = 0
        self._highlight = QRect()
        self._tip_rect = QRect()
        self._on_page = None

        # 不用布局：卡片按固定宽度、自适应高度手动定位
        self.card = widgets.GlassCard(self, radius=14, alpha=246)
        self.card.setFixedWidth(340)
        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(18, 15, 18, 15)
        inner.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.step_label = QLabel()
        self.step_label.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
        self.step_label.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        top.addWidget(self.step_label)
        top.addStretch(1)
        self.skip_btn = widgets.AppButton("跳过", None, "ghost", "sm")
        self.skip_btn.clicked.connect(lambda: self._finish(False))
        top.addWidget(self.skip_btn)
        inner.addLayout(top)

        self.title = QLabel()
        self.title.setFont(theme.font(14, theme.QFont.Weight.DemiBold))
        self.title.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.title.setWordWrap(True)
        inner.addWidget(self.title)

        self.body = QLabel()
        self.body.setFont(theme.font(11.5))
        self.body.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.body.setWordWrap(True)
        inner.addWidget(self.body)

        self.tip = QLabel()
        self.tip.setFont(theme.font(11.5))
        self.tip.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.tip.setWordWrap(True)
        inner.addWidget(self.tip)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch(1)
        self.prev_btn = widgets.AppButton("上一步", None, "ghost", "sm")
        self.prev_btn.clicked.connect(self._prev)
        foot.addWidget(self.prev_btn)
        self.next_btn = widgets.AppButton("下一步", None, "primary", "sm")
        self.next_btn.clicked.connect(self._next)
        foot.addWidget(self.next_btn)
        inner.addLayout(foot)

        self.hide()

    # ---------------------------------------------------------- 控制
    def start(self):
        self._index = 0
        self.show()
        self.raise_()
        self.setGeometry(self.parentWidget().rect())
        self._apply()

    def _goto(self, index: int):
        self._index = max(0, min(index, len(self._steps) - 1))
        self._apply()

    def _next(self):
        if self._index >= len(self._steps) - 1:
            self._finish(True)
            return
        self._goto(self._index + 1)

    def _prev(self):
        self._goto(self._index - 1)

    def _finish(self, completed: bool):
        self.hide()
        self.finished.emit(completed)

    def set_page_handler(self, handler):
        self._on_page = handler

    def _apply(self):
        step = self._steps[self._index]
        if self._on_page is not None:
            self._on_page(step.page)
        self.step_label.setText(f"第 {self._index + 1} / {len(self._steps)} 步")
        self.title.setText(step.title)
        self.body.setText(step.body)
        self.tip.setText(step.tip)
        self.prev_btn.setVisible(self._index > 0)
        self.next_btn.setText("完成" if self._index >= len(self._steps) - 1 else "下一步")
        # 切页后布局需要一轮事件循环才能拿到目标控件的最终坐标；
        # 目标控件可能在切页后仍需重新排布，多补两次定位
        QTimer.singleShot(60, self._relayout)
        QTimer.singleShot(180, self._relayout)

    def _relayout(self):
        if not self.isVisible():
            return
        self.setGeometry(self.parentWidget().rect())
        step = self._steps[self._index]
        target = step.target() if callable(step.target) else step.target
        if target is not None and target.isVisible() and target.width() > 0:
            top_left = target.mapTo(self.parentWidget(), QPoint(0, 0))
            self._highlight = QRect(
                top_left.x() - self.MARGIN, top_left.y() - self.MARGIN,
                target.width() + self.MARGIN * 2, target.height() + self.MARGIN * 2,
            )
        else:
            self._highlight = QRect()
        self.card.adjustSize()
        w, h = self.card.width() + 2, self.card.height() + 2
        parent = self.rect()
        if self._highlight.isValid():
            below = self._highlight.bottom() + 14
            y = below if below + h <= parent.bottom() - 16 else max(16, self._highlight.top() - h - 14)
            x = min(max(16, self._highlight.left()), max(16, parent.right() - w - 16))
            # 靠右的目标（如“新增考试”）把气泡右对齐，避免气泡盖住页面右上角
            if self._highlight.right() > parent.width() - 320:
                x = max(16, parent.right() - w - 24)
            # 气泡不能压住高亮区域
            card_rect = QRect(x, y, w, h)
            if card_rect.intersects(self._highlight):
                y = max(16, self._highlight.top() - h - 14)
                if y < 16:
                    y = min(parent.bottom() - h - 16, self._highlight.bottom() + 14)
                card_rect = QRect(x, y, w, h)
        else:
            x = (parent.width() - w) // 2
            y = (parent.height() - h) // 2
        self.card.move(x, y)
        self._tip_rect = QRect(x, y, w, h)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    # ---------------------------------------------------------- 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mask = QPainterPath()
        mask.addRect(QRectF(self.rect()))
        if self._highlight.isValid():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(self._highlight), 12, 12)
            mask = mask.subtracted(hole)
            p.fillPath(mask, QColor(12, 20, 38, 84))
            pen = QPen(QColor(10, 132, 255, 210), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self._highlight), 12, 12)
        else:
            p.fillPath(mask, QColor(12, 20, 38, 84))
        p.end()

    def mousePressEvent(self, event):
        # 遮罩本身吃掉点击，避免误触下面的页面
        if not self.card.geometry().contains(event.position().toPoint()):
            event.accept()
            return
        super().mousePressEvent(event)


def build_default_steps(home_btn, todo_input, exam_add_btn) -> list[_Step]:
    """三步：建课 → 加待办 → 记考试。"""
    return [
        _Step(0, home_btn, "先把课表填上",
              "课程表是后面的基础。点「打开课程表」，或在课表页点任意空白格子，都能新建一门课。",
              "课程名称必填，老师、地点、节次、周次都可以慢慢补。"),
        _Step(2, todo_input, "每天要做的事，写一行就行",
              "在输入框敲一行字、按回车，就多了一条待办；想换类型就点下面的「每日 / 每周 / 一次」。",
              "完成后勾选方框，进度条会自动前进，右键还能看到完成记录。"),
        _Step(3, exam_add_btn, "把考试也记下来",
              "点「新增考试」，填科目、日期、开始时间和时长，主页就会出现倒计时。",
              "复习进度可以随时改，临近考试时卡片会变成「即将开始」。"),
    ]
